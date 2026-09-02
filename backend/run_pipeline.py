import os
from dotenv import load_dotenv
from pipeline import load_pipeline, process_call, SAMPLE_RATE
from database import save_audio_insights, save_utterances, save_recording

load_dotenv()

# Load the pipeline once
pipe = load_pipeline()

# Change this to one of your actual audio files
AUDIO_FILE = "heya_sample_calls/audio0.wav"
CALL_ID    = "call_test_001"   # the one we inserted in pgAdmin earlier

print(f"Processing: {AUDIO_FILE}")
turn_df, summary = process_call(AUDIO_FILE, pipe, SAMPLE_RATE)

print(f"\nEngagement : {summary['engagement_score']}")
print(f"Flow       : {summary['conversation_flow']}")
print(f"Turns      : {summary['total_turns']}")

# Save to database
save_audio_insights(CALL_ID, summary)
save_utterances(CALL_ID, turn_df)
save_recording(CALL_ID, AUDIO_FILE)

print("\n✅ Done — check pgAdmin audio_insights table")