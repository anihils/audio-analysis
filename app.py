from google.cloud import speech # Imports the Google Cloud client library
import subprocess

gcs_input_folder = "gs://audio-analysis/input/"
gcs_optimised_folder = "gs://audio-analysis/optimised/"
gcs_transcripts = "gs://audio-analysis/transcripts/"
local_input_folder = "input_files/"
local_transcript_folder = "transcripts/"

# Instantiates a client
client = speech.SpeechClient()

# Run ffprobe to extract metadata of audio file
# Can also be used to confirm audio metadata/successful conversion to .flac audio file
def probe_audio(audio_file):
    metadata_file_name = "metadata.txt"
    file = open(metadata_file_name, "w") # file destroyed in the same function

    # Run ffprobe to extract audio information: ffprobe outputs to stderr
    subprocess.run(["ffprobe", audio_file, "-hide_banner"], stderr=file)
    file.close()

    metadata = {}
    with open(metadata_file_name, "r") as file:
        for line in file.readlines():
            if "Duration" in line:
                duration = line.strip().split("Duration: ")[1].split(',')[0].split(':')
                minutes = int(duration[0]) * 60 + int(duration[1])
                metadata['duration'] = minutes
            elif "Stream" in line and "Audio:" in line: # Line containing format, sample_rate, and number of channels
                parts = line.split("Audio: ")[1].split(',')
                metadata['codec'] = parts[0].strip()
                metadata['sample_rate'] = parts[1].strip().rstrip(" Hz")
                metadata['channels'] = parts[2].strip()
                break
    subprocess.run(["rm", metadata_file_name]) # delete metadata.txt file
    return metadata

# Writes all the files in a given bucket to a given file (does not list recursively)
def list_gcs_folder_contents(folder_uri, contents_file_name):
    file = open(contents_file_name, "w")
    subprocess.run(["gsutil", "ls", folder_uri + "*.*"], stdout=file)
    file.close()
    return

# Grabs file name from gcs_uri
def get_file_name(uri):
    #path = uri.split(gcs_folder_name) # removes bucket/folder name from gcs_uri
    #return path[1]
    path = uri.split('/')
    return path[-1]

# Converts audio file to flac codec (probe for number of channels)
# If ffprobe fails, num_channels passed = -1
def format_audio(gcs_uri):
    # 1) Download audio file from GCS into local_input_folder
    subprocess.run(["gsutil", "cp", gcs_uri, local_input_folder])
    file_name = get_file_name(gcs_uri)
    file_path = local_input_folder + file_name
    
    # 2) Check metadata using ffprobe
    convert_mono = False
    num_channels = 1
    metadata = probe_audio(file_path) # check whether metadata is empty
    if len(metadata) == 0: # ffprobe metadata not found - check format of metadata.txt
        print('ERROR: Empty metadata dictionary passed')
        return None
    else:
        channels = metadata['channels']
        duration = metadata['duration'] # audio length in minutes
        if channels == "stereo":
            num_channels = 2
        elif channels == "5.1":
            num_channels = 6
        else:
            convert_mono = True

        if metadata['codec'] != 'flac': # 3) Conversion to .flac needed
            flac_file_path = file_path.split('.')[0] + '.flac' # includes input folder name
            flac_file_name = file_name.split('.')[0] + '.flac'

            if convert_mono is True: # -ac 1: mono track
                subprocess.run(["ffmpeg", "-i", file_path, "-ac", "1", flac_file_path])
            else:
                subprocess.run(["ffmpeg", "-i", file_path, flac_file_path])

            # 4) Place .flac file in storage bucket
            subprocess.run(["gsutil", "cp", flac_file_path, gcs_optimised_folder])
            gcs_uri_flac = gcs_optimised_folder + flac_file_name # gcs uri of optimised file
            return {gcs_uri_flac : [num_channels, duration]} 

        else: # No conversion needed: return same uri
            return {gcs_uri : [num_channels, duration]}

# TODO: 2 - Remove background noise and increase volume of speech
def optimise_audio(gcs_uri_flac):
    return 

# Use Google Cloud's Speech-To-Text API to transcribe audio files
def transcribe_audio(gcs_uri, transcript_file):
    format_data = format_audio(gcs_uri) # convert to .flac file
    gcs_uri_flac = list(format_data.keys())[0] # grab gcs_uri of converted file
    num_channels, duration = format_data[gcs_uri_flac]
    if format_data is None:
        print("ffprobe failed to extract metadata: skipping transcription")
        return

    optimise_audio(gcs_uri_flac) # decrease background noise
    print(gcs_uri_flac, "is optimised for transcription")

    audio = speech.RecognitionAudio(uri=gcs_uri_flac)
    additional_languages = ['hi','ta']

    # Sample rate and number of channels taken from FLAC header - do not have to specify in config
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
        language_code="en-US",
        alternative_language_codes=additional_languages,
        audio_channel_count=num_channels,
        enable_separate_recognition_per_channel=True
    )

    # Detects speech in the audio file
    if duration > 1:
        print('Asynchronous speech recognition')
        operation = client.long_running_recognize(config=config, audio=audio)
        response = operation.result(timeout=90)
    else:
        print('Synchronous speech recognition')
        response = client.recognize(config=config, audio=audio)

    transcript = open(transcript_file, "w")
    for result in response.results:
        transcript.write("{}\n".format(result.alternatives[0].transcript))
    transcript.close()

    # Copies files from local transcripts folder to GCS transcripts folder
    subprocess.run(["gsutil", "cp", transcript_file, gcs_transcripts])

# Clears local folders
def clean_local():
    subprocess.run(["rm", "-r", local_input_folder]) # delete folder created to temporarily store audios
    subprocess.run(["rm", "-r", local_transcript_folder])

# Clears GCS bucket folders 
def clean_gcs():
    subprocess.run(["gsutil", "-m", "rm", "-r", gcs_optimised_folder + "*.*"])
    subprocess.run(["gsutil", "-m", "rm", "-r", gcs_transcripts + "*.*"])

def transcribe_all():
    contents_file_name = "input_files.txt"
    list_gcs_folder_contents(gcs_input_folder, contents_file_name)
    
    # Create new directories for storing audio files from storage bucket and output
    subprocess.run(["mkdir", local_input_folder]) 
    subprocess.run(["mkdir", local_transcript_folder]) 

    with open(contents_file_name, "r") as contents:
        for gcs_uri in contents.readlines():
            gcs_uri = gcs_uri.strip() # DO NOT REMOVE - readlines() returns a \n at the end
            file_name = get_file_name(gcs_uri)
            transcript_file = local_transcript_folder + file_name.split('.')[0] + '.txt'
            transcribe_audio(gcs_uri, transcript_file) # transcript written to .txt file

    subprocess.run(["rm", contents_file_name])

transcribe_all()
clean_local()
clean_gcs()