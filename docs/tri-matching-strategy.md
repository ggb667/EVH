# TRI matching strategy

TRI is the search/ranking strategy for EVH RAG dictionary lookup after client and patient identification.

## Goal

Support fast lookup across multiple dictionary tables so PDF search can find relevant terms regardless of type:

- medications
- treatments
- vet terms

The storage model stays simple. The search layer does the work.

## Core rules

1. Exact matches are supported and should score highest.
2. Prefix matches are supported for term fragments from 3 to 7 characters.
3. Ranking uses the first 3 characters as the primary signal.
4. Search spans multiple dictionary tables and returns a unified ranked result set.
5. Tokenization must preserve letters, numbers, and symbols when useful for matching.
6. Non-character symbols also act as secondary breaks so subfragments can be searched independently.

## Tokenization behavior

Examples:

- `AX-453` should produce usable search fragments such as `AX-`, `AX`, and `453`.
- `453` should be searchable as its own leading fragment.
- `NT` should be searchable as a shorthand alias when a treatment alias row exists.

The practical effect is:

- keep the raw text
- normalize case
- split on whitespace and punctuation
- retain symbol-rich fragments where they help disambiguate or match a known code-like term

## Candidate generation

For each canonical row and alias row:

1. Check exact string match first.
2. Check normalized exact match next.
3. Check prefix fragments from 3 to 7 characters.
4. Check token fragments generated from punctuation-aware splitting.
5. Merge all hits into one ranked result list.

## Scoring

Suggested score ordering:

- exact canonical match
- exact alias match
- strong prefix match on the first 3 characters
- longer prefix match from 4 to 7 characters
- token-fragment match from symbol-aware splitting

The exact weights can change later. The important part is the order.

## Search flow

1. Identify client and patient.
2. Search the PDF and dictionary tables for candidate terms.
3. Rank exact matches above prefix matches.
4. Combine results across all dictionary tables.
5. Feed the best hits into timeline extraction and summary generation.

## Implementation note

This can be done in Python with standard string handling and regex helpers, or with database text-search support where useful.
The structure should stay flexible enough to support exact lookup, prefix lookup, and symbol-aware fragments without forcing a deeper taxonomy model.
