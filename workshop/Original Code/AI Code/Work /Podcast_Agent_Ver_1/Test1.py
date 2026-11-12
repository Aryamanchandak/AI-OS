from google import genai

client = genai.Client(api_key="AQ.Ab8RN6LepxR48VAHGppAsXDRwFxBZiiI_QpqXIZ7OSxKnwv0Yw")

interaction = client.interactions.create(
    model="gemini-3.5-flash",
    input="Explain how AI works in a few words"
)

print(interaction.output_text)