from google import genai

client = genai.Client(api_key="AQ.Ab8RN6I1VBT1XbDqKjH8TDVIXvvDnGglxNNKyqh0NUxAEjEJJg")

response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents="How does AI work?"
)
print(response.text)