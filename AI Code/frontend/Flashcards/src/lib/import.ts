import type { ImportCard } from '../types'

export function parseCardJson(input: string): ImportCard[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(input)
  } catch {
    throw new Error('That is not valid JSON. Check commas and quotation marks.')
  }
  const candidate = Array.isArray(parsed) ? parsed : (parsed as { cards?: unknown })?.cards
  if (!Array.isArray(candidate)) throw new Error('Use a JSON array, or an object with a “cards” array.')
  return candidate as ImportCard[]
}

export function promptForUnit(unit: string): string {
  return `Create 12 useful German flashcards from ${unit}. Return only JSON in this exact shape: {"cards":[{"term":"","article":"der|die|das|null","plural":"","ipa":"","gloss":"","example_de":"","example_en":"","note":"","tags":[""],"unit":"${unit}"}]}. Keep examples natural, A1–B1 level, and verify German noun gender.`
}

const starterVocabulary = [
  ['Alltag', 'der', 'everyday life', 'Mein Alltag beginnt um sieben Uhr.', 'My everyday life starts at seven.'],
  ['Erfahrung', 'die', 'experience', 'Das war eine gute Erfahrung.', 'That was a good experience.'],
  ['Gespräch', 'das', 'conversation', 'Wir führen ein kurzes Gespräch.', 'We are having a short conversation.'],
  ['erklären', null, 'to explain', 'Kannst du das bitte erklären?', 'Can you explain that, please?'],
  ['gemeinsam', null, 'together', 'Wir lernen gemeinsam Deutsch.', 'We learn German together.'],
  ['Möglichkeit', 'die', 'possibility', 'Es gibt noch eine Möglichkeit.', 'There is one more possibility.']
] as const

/** Keyless, deterministic draft generation keeps the workflow useful offline. */
export function generateLocalDrafts(unit: string): ImportCard[] {
  const cleanUnit = unit.trim() || 'German vocabulary'
  return starterVocabulary.map(([term, article, gloss, exampleDe, exampleEn]) => ({
    term,
    article,
    plural: article ? `${term}${term.endsWith('e') ? 'n' : 'e'}` : '',
    gloss,
    example_de: exampleDe,
    example_en: exampleEn,
    note: `Draft for ${cleanUnit} — verify against your course material.`,
    tags: [article ? 'noun' : term.endsWith('en') ? 'verb' : 'phrase', 'generated-draft'],
    unit: cleanUnit
  }))
}

export async function generateCards(endpoint: string, apiKey: string, model: string, unit: string): Promise<ImportCard[]> {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: 'You are a careful German language teacher. Return valid JSON only.' },
        { role: 'user', content: promptForUnit(unit) }
      ],
      response_format: { type: 'json_object' }
    })
  })
  if (!response.ok) throw new Error(`Generation failed (${response.status}). Check the endpoint, model, and key.`)
  const data = await response.json() as { choices?: Array<{ message?: { content?: string } }> }
  const content = data.choices?.[0]?.message?.content
  if (!content) throw new Error('The model returned no card data.')
  return parseCardJson(content)
}
