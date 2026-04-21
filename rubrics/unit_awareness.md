# Rubric: Unit awareness

The corpus contains a trap page where a temperature range is stated as
"**32 to 104**" without an explicit unit on the same line; a footnote clarifies
it is Fahrenheit. The primary (metric) datasheet clearly states the range in
°C. The agent should produce an answer that is internally consistent and, when
stating a temperature range, includes the unit.

## Pass criteria
- The answer includes units explicitly (°C or °F).
- If the agent quotes "32 to 104" it must also attach the correct unit (°F).

## Fail criteria
- The answer states a range without units.
- The answer conflates °C and °F (e.g., says the R1 operates "32°C to 104°C").
