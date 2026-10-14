# ============================================================
# STEP 2 : PODCAST TRANSCRIPT
# ============================================================

podcast_prompt = f"""

You are creating a professional financial podcast.

Requirements:

- Natural conversational style
- Not robotic
- Focus on investment insights
- Discuss:
    - Business Overview
    - Industry Overview
    - Financial Performance

- Explain numbers in simple language
- Make it sound like a real investing podcast
- Keep it concise
- Length: approximately 1-2 minutes
"""

transcript_response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=podcast_prompt
)

transcript = transcript_response.text

print("=" * 100)
print("TRANSCRIPT GENERATED")
print("=" * 100)

print(transcript)

with open("podcast_transcript.txt", "w", encoding="utf-8") as f:
    f.write(transcript)

# ============================================================
# STEP 3 : TEXT TO SPEECH
# ============================================================

tts_response = client.models.generate_content(
    model="gemini-2.5-flash-preview-tts",
    contents=transcript,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Kore"
                )
            )
        )
    )
)

audio_data = (
    tts_response.candidates[0]
    .content.parts[0]
    .inline_data.data
)

# ============================================================
# SAVE AUDIO
# ============================================================

output_file = "Gen_podcast.wav"

with wave.open(output_file, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(24000)
    wf.writeframes(audio_data)

print(f"Saved: {output_file}")