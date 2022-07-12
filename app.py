from google.cloud import speech # Imports the Google Cloud client library
import subprocess

input_bucket = "gs://audio-analysis-input-bucket"
input_folder = "input_files"
output_folder = "transcripts"
optimised_bucket = "gs://audio-analysis-optimised-bucket"

# Instantiates a client
client = speech.SpeechClient()

# Writes all the files in a given bucket to a given file 
def list_bucket_contents(bucket_uri, bucket_contents_file_name):
    file = open(bucket_contents_file_name, "w")
    subprocess.run(["gsutil", "ls", bucket_uri], stdout=file)
    file.close()
    return

# Function to grab file name from gcs_uri 
def get_file_name(uri, bucket_name):
    path = uri.split(bucket_name)
    return path[1][1:]

# Run ffprobe to extract metadata of audio file
# Can also be used to confirm audio metadata/successful conversion to .flac audio file
# TODO: 3 - Add duration to metadata
def probe_audio(audio_file):
    metadata_file_name = "metadata.txt"
    file = open(metadata_file_name, "w") # file destroyed in this function
    # Run ffprobe to extract audio information
    subprocess.run(["ffprobe", audio_file, "-hide_banner"], stderr=file)
    file.close()
    metadata = {}

    with open(metadata_file_name, "r") as file:
        for line in file.readlines():
            if "Stream" in line and "Audio:" in line: # Line containing format, sample_rate, and number of channels
                parts = line.split("Audio: ")[1].split(',')
                metadata['codec'] = parts[0].strip()
                metadata['sample_rate'] = parts[1].strip().rstrip(" Hz")
                metadata['channels'] = parts[2].strip()
                break
    subprocess.run(["rm", metadata_file_name])
    return metadata

# Converts audio file to flac codec (probe for number of channels)
# TODO: 3 - If metadata is empty send signal to transcribe
def format_audio(gcs_uri):

    # 1) Download audio file from GCS into input_folder
    subprocess.run(["gsutil", "cp", gcs_uri, input_folder])

    file_name = get_file_name(gcs_uri, input_bucket).strip()
    file_path = input_folder + "/" + file_name

    # 2) Check metadata using ffprobe
    convert_mono = False
    num_channels = 1
    metadata = probe_audio(file_path) # check whether metadata is empty
    if len(metadata) == 0: # ffprobe metadata not found - check format of metadata.txt
        print('Empty metadata dictionary passed to optimise_audio()')
        return
    else:
        channels = metadata['channels']
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
            subprocess.run(["gsutil", "cp", flac_file_path, optimised_bucket])
            gcs_uri_flac = optimised_bucket + "/" + flac_file_name # gcs uri of optimised file
            return {gcs_uri_flac : num_channels} 

        else: # No conversion needed: return same uri
            return {gcs_uri : num_channels}

# TODO: 2 - Remove background noise and increase volume of speech
def optimise_audio(gcs_uri_flac):
    return 

# Use Google Cloud's Speech-To-Text API to transcribe audio files over 1 minute
# TODO: 1 - Write transcriptions to files in GCS
# TODO: 2 - Create transcribe case for short audios (client.recognize)
# TODO: 3 - Add support for multiple languages (Hindi, Tamil)
def transcribe_long_audio(gcs_uri, output_file):
    uri_channels = format_audio(gcs_uri) # convert to .flac file
    gcs_uri_flac = list(uri_channels.keys())[0] # grab gcs_uri of converted file
    num_channels = uri_channels[gcs_uri_flac]
    optimise_audio(gcs_uri_flac) # decrease background noise

    print(gcs_uri_flac, "is optimised for transcription")

    audio = speech.RecognitionAudio(uri=gcs_uri_flac)

    # Sample Rate and number of channels taken from FLAC header - do not have to specify in config
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
        language_code="en-US",
        audio_channel_count=num_channels,
        enable_separate_recognition_per_channel=True
    )

    # Detects speech in the audio file
    operation = client.long_running_recognize(config=config, audio=audio)
    response = operation.result(timeout=90)

    transcript = open(output_file, "w")
    for result in response.results:
        transcript.write("{}\n\n".format(result.alternatives[0].transcript))
    transcript.close()

# TODO: 3 - Delete contents of given bucket
def clear_bucket(bucket_name):
    pass

def transcribe_all():
    bucket_contents_file_name = "bucket_contents.txt"
    list_bucket_contents(input_bucket, bucket_contents_file_name)

    # Create new directories for storing audio files from storage bucket and outputs
    subprocess.run(["mkdir", input_folder]) 
    subprocess.run(["mkdir", output_folder]) 

    with open(bucket_contents_file_name, "r") as bucket:
        for gcs_uri in bucket.readlines():
            file_name = get_file_name(gcs_uri, input_bucket)
            transcript_file = output_folder + "/" + file_name.split('.')[0] + '.txt'
            transcribe_long_audio(gcs_uri.strip(), transcript_file)

    # Remove created files and folders
    subprocess.run(["rm", "-r", input_folder]) # delete folder created to temporarily store audios
    subprocess.run(["rm", bucket_contents_file_name])
    clear_bucket(optimised_bucket)

transcribe_all()