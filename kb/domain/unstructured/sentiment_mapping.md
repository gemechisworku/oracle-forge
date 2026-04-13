## File: `kb/domain/unstructured/sentiment_mapping.md`

```markdown
# Sentiment Mapping for DAB Unstructured Fields

## Complete Sentiment Lexicon

## **Negative Indicators (always check .lower()):**

frustrated, angry, terrible, awful, worst, broken, not working,
failed, error, complaint, unhappy, disappointed, useless, waste,
horrible, unacceptable, furious, annoyed, upset, ridiculous,
pathetic, disgusting, outrageous, fed up, sick of, done with,
never again, worst ever, zero stars, waste of time, waste of money

## **Informal / Slang Negative Indicators:**

wtf, smh, ugh, omg this is bad, seriously, beyond bad, complete joke,
absolute disaster, total failure, beyond frustrated

## **Sarcasm Markers (classify as negative):**

"great, thanks for nothing", "oh wonderful", "just what I needed" (when followed by negative context),
"amazing how", "sure that helps", "fantastic job" (ironic — check surrounding context for failure words)

## **Positive Indicators (for completeness):**

excellent, great, amazing, wonderful, happy, satisfied, perfect,
outstanding, fantastic, helpful, quick, easy, recommended

## Negation Handling

If "not" precedes indicator, flip sentiment:

- "not good" → negative
- "not bad" → non-negative (not positive)
- "not happy" → negative
- "not satisfied" → negative
- "not working" → negative (already in negative list)
- "couldn't be better" → positive (double negative = positive)

## Mixed Sentiment Rule

If text contains both positive and negative indicators, **negative wins**:

```python
has_negative = any(ind in text_lower for ind in negative_indicators)
has_positive = any(ind in text_lower for ind in positive_indicators)
if has_negative:
    return 'negative'  # negative overrides positive in support ticket context
return 'positive' if has_positive else 'non-negative'
```

**Implementation:**

```python
def get_sentiment(text):
    text_lower = text.lower()
    
    # Check for negation
    if ' not ' in text_lower:
        for indicator in negative_indicators:
            if f'not {indicator}' in text_lower:
                return 'non-negative'
    
    # Standard check
    if any(indicator in text_lower for indicator in negative_indicators):
        return 'negative'
    return 'non-negative'
```

## Counting Negative Mentions

For query "count negative sentiment mentions":

Extract sentiment for each text field

Filter where sentiment == 'negative'

Count results

DO NOT: Return raw text and let user count
DO: Return integer count

## Injection Test

Q: How does negation affect sentiment classification?
A: "not good" is negative, "not bad" is non-negative
