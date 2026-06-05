# Question Answering Skill

(No learned rules yet. Rules will be added through the reflection process.)

## Answer Normalization Rules
1. **Answer with the most generic, canonical form.** If the gold answer is a category (e.g., 'Anti-perspirant', 'an insulator'), do not list specific examples. If the gold answer is a single word or short phrase, do not include extra modifiers or descriptive clauses.
2. **Drop titles and honorifics** unless they are essential to distinguish the entity (e.g., answer 'Arthur' not 'Chester A. Arthur', 'Drake' not 'Sir Francis Drake').
3. **Use the exact wording that best matches the question.** Prefer singular nouns over plural if the question uses singular form. If the question asks for a "dessert" answer 'pudding' not 'hasty pudding'. If the question asks for a "term" answer 'an insulator' not 'insulators'.

## Answer Extraction Rules

0. **Treat the question as a search key into the context.** The question's exact wording (including quoted phrases, named entities, and relational words) is the best search query for locating the answer in the provided documents. Do not rely on external knowledge or paraphrase the question; instead, match its terms directly against the text.

1. **Extract the exact answer entity from the context.** Do not provide descriptions, categories, or paraphrases. For example, if the gold answer is 'Italy', do not say 'the country of Italy' or 'a European nation'. Use the question's phrasing as a direct clue to identify the precise word or short phrase that answers it.

2. **Be concise.** Provide only the answer inside `<answer>...</answer>` tags. A single word or short phrase is almost always sufficient. Do not repeat the question wording in the answer.

3. **Ignore clever, punny, or descriptive phrasing in the question.** Focus on the underlying entity being asked—extract only the canonical name or term that satisfies the query, without explaining wordplay or adding context. The answer is almost always a contiguous word or short phrase that appears verbatim in the context; do not infer, summarize, or combine multiple parts of the context.

3. **Resolve contradictions by prioritizing explicit statements.** If the context contains conflicting information (e.g., 'third largest' vs. 'largest'), rely on the most direct, explicit statement that answers the question.

1. **Identify the entity type asked by the question.** Determine whether the question asks for a person, place, time period, event, or thing. Answer only with the specific name or term of that entity, not a description of it. For example, if the question is 'Timonium', answer 'Maryland' (the place where it's located) not 'a census-designated place in Maryland'.

2. **Answer with the exact phrasing that fills the question's blank or completes its prompt.** If the question ends with 'this tropical fruit', the answer is the fruit name exactly as given in context (e.g., 'Pineapples', not 'pineapple'). Do not change number, capitalization, or modifiers unless the skill rules explicitly require it.

3. **When the question consists of a short phrase with a preposition (e.g., 'Henry Ward Beecher for adultery'), parse it carefully: the word after the preposition often indicates the answer category (e.g., 'for' may mean 'during the time of'). Answer with the time period, location, or category implied by the preposition, not the named entity.**

1. **Extract the exact answer entity from the context.** Do not provide descriptions, categories, or paraphrases. For example, if the gold answer is 'Italy', do not say 'the country of Italy' or 'a European nation'. Use the question's phrasing as a direct clue to identify the precise word or short phrase that answers it.

2. **Be concise.** Provide only the answer inside `<answer>...</answer>` tags. A single word or short phrase is almost always sufficient. Do not repeat the question wording in the answer.

3. **Resolve contradictions by prioritizing explicit statements.** If the context contains conflicting information (e.g., 'third largest' vs. 'largest'), rely on the most direct, explicit statement that answers the question.

### Handling Clever or Descriptive Questions

### Pattern: Entity-from-Description Matching

When a question describes an entity using a category label or descriptive phrase (e.g., 'this aerospace company', 'this potable', 'this miniseries', 'this flavor ice cream', 'this country'), answer with ONLY the specific name of the entity found in the context. Do not repeat or paraphrase the descriptive category. For example, if the question asks 'this tropical fruit', answer 'Pineapples' not 'the tropical fruit pineapples'; if the question asks 'this flavor ice cream', answer 'vanilla' not 'vanilla ice cream'.

**For all clever/descriptive questions**, the answer is the specific entity that matches the gold answer exactly. Do not elaborate, explain the pun, or include any descriptive words from the question.

### Handling Prepositional or Category-Hint Questions

Some questions end with a prepositional phrase that signals the answer category (e.g., 'in this city', 'under this country's rule', 'this woman's NYC gallery', 'for these people'). Treat the prepositional phrase as a prompt for the missing entity type and answer with ONLY the name that belongs in the slot. Do not repeat the category or description — answer with the specific entity (e.g., if the question ends with 'in this city', answer 'Richmond', not 'the city of Richmond' or 'Richmond, Virginia').

### Handling Constrained-Choice Questions

Some questions present a set of explicit options (e.g., 'Of 2, 5 or 10, the number of eyes on a bee') or constrain the answer format by specifying a count (e.g., 'this 3-word actors' phrase'). When the question offers a short list or sets a numeric/structural limit, select the option that exactly matches the context — do not generate an answer outside the given set or format. For example, if the question asks 'Of 2, 5 or 10, the number...', answer with one of those numbers (e.g., '5'), not a different number or a descriptive phrase.

Some questions use wordplay, puns, metaphors, or clever phrasing (e.g., 'To Dustin Hoffman this '82 film was a drag' or 'It's the cry of a sheep or goat'). Despite the playful framing, these questions still ask for a precise entity. Extract that entity directly — do not explain the pun or describe the play on words in your answer.

**For descriptive sentence questions** (e.g., 'This 113-mile sand bar along Texas' Gulf Coast is the state's largest island' or 'It's thought Saladin offered this fruity dessert, cousin to ice cream, to Richard I during the Crusades'), extract only the specific named entity from the context (e.g., 'Padre Island', 'sherbet'). Do not include descriptive words from the question or context in your answer.

**For fill-in-the-blank or descriptive prompts** (e.g., 'Bridge to ___' or 'high point of this peachy state'), answer with only the missing word or phrase. Do not repeat the surrounding description. Answer with exactly the word or phrase that fills the blank — do not add definite or indefinite articles ('the', 'a', 'an') unless they are part of the intended answer. For example, if the question is "A joke says that when you play country music this way, your wife, your dog & your car return", answer 'backwards' not 'the backwards' or 'play backwards'.

Similarly, if the gold answer in context is 'violet' (without an article), do not answer 'the violet'.

## Pluralization and Number Consistency

1. **Match the number used in the gold answer when the question implies a specific count or category.** If the context uses a plural form (e.g., 'Pineapples') and the question asks for 'this tropical fruit' (singular), still prefer the exact form from the context unless it conflicts with canonical form rules. When in doubt, use the form that appears in the most direct answer-bearing sentence.

2. **If the entity has a well-known modifier that is part of its canonical name (e.g., 'Brown pelican'), include that modifier.** Do not drop an adjective that disambiguates the entity from a broader category.

## Determiner Normalization
1. **Drop leading determiners ('a', 'an', 'the') from the answer when the entity is a proper noun (e.g., a person, place, or title).** For example, if the gold answer is 'the Sahara' or 'the Adirondacks', answer 'Sahara' or 'Adirondacks'. If the gold answer is a common noun or category, keep the determiner only if it is essential to the meaning (e.g., 'an insulator' retains 'an').

## Canonical Name Priority
When the context provides multiple ways to refer to the same entity (e.g., a full formal name, a specific sub-type, or a broader/generic name), prefer the **most canonical or commonly recognized form** that matches the expected answer type. For example, if the context mentions 'sea lamprey' but the expected answer is 'the lamprey', answer 'the lamprey'. Do not add extra specific adjectives (like 'sea' or 'modern') unless they are part of the indisputable gold answer.

## Handling Indirect or Metonymic References

1. **Resolve metonymic or descriptive references to their canonical entity.** If the question describes an entity indirectly (e.g., 'series on these of the '30s & '40s' referring to trains, or '1961 classic' referring to Romeo and Juliet) or uses a specific location to hint at a broader institution (e.g., 'this state university at Superior' pointing to the University of Wisconsin system), answer with the gold-standard authoritative entity from the context, not the surface-level specific item. Do not give a year or a specific campus if the question expects the work name or the system-level institution.
2. When the question is phrased as a puzzle or riddle that points to a known entity, resolve the reference to the canonical entity rather than the literal words or numbers present in the context.

<!-- SLOW_UPDATE_START -->
### Exact Answer Matching — Three Mandatory Checks
Before outputting your answer, verify these three conditions:

1. **Every word in the gold answer is present in your answer in the correct order.** If the gold answer is 'Pituitary gland', your answer must include both 'Pituitary' AND 'gland'. Do not drop any word that appears in the gold answer. If the gold answer is 'Showboat' (one word), do not split it into 'Show Boat' (two words). If the gold answer is 'Bagpipes' (capitalized, plural), answer 'Bagpipes' not 'bagpipe'.

2. **Do not add any words that are not in the gold answer.** No extra titles, modifiers, middle initials, nicknames, or descriptive words. If the gold answer is 'Lyndon Johnson', do not output 'Lyndon B. Johnson'. If the gold answer is 'John Brown', do not add 'John Brown's' or any other words.

3. **Match exactly — spelling, spacing, capitalization, and punctuation.** 'Showboat' ≠ 'Show Boat'. 'Bagpipes' ≠ 'bagpipe'. 'Pituitary gland' ≠ 'pituitary'. Verify character-by-character.

When the question asks for a museum named after a person (e.g., 'museum named for this Civil War figure'), the person's name IS the answer — find the exact name in the context and output it directly. Do not get confused and leave the answer blank.

### Handling Spacing Variants in Entity Names
If the gold answer appears as a single word (e.g., 'Showboat', 'Adirondacks') and the context uses a multi-word form (e.g., 'Show Boat') or vice versa, always use the EXACT capitalization and spacing of the gold answer. Do not add spaces within a gold answer that is one word, and do not merge words that are separate in the gold answer. The gold answer's formatting is authoritative.

### Answer Must Be a Complete Extract — No Partial Dropping
When the context contains a phrase that exactly matches the question's information (e.g., 'the pituitary gland contains a hormone'), the answer must include ALL words from that phrase that correspond to the answer entity. If the gold answer is 'Pituitary gland', do NOT strip 'gland' because it seems like a category word. Is 'gland' part of the gold answer? If yes, include it. Only drop words if a specific rule in the main skill says they must be dropped AND the gold answer confirms the shorter form.
<!-- SLOW_UPDATE_END -->
