In app.py, change values of `gcs_input_folder` to bucket folder with audio files to be transcribed, `gcs_optimised_folder` to a personal bucket for temporary storage of audio files, and 'gcs_transcripts to a personal bucket folder for storing transcriptions of the audio files.\
Use of storage buckets and Speech-To-Text API requires a key to a Google Service Account with roles of 'Cloud Speech-to-Text Service Agent' and 'Storage Admin'. Use 'Owner' role for convenience.\
Save json file of the key in a safe location and save `export GOOGLE_CLIENT_CREDENTIALS="path/to/key.json"` in ~/.bashrc
