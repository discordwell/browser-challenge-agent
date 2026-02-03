# Browser Challenge Agent

An AI-powered browser automation agent designed to solve the [Browser Navigation Challenge](https://serene-frangipane-7fd25b.netlify.app) - 30 UI challenges testing modal handling, form interaction, and navigation skills.

## Challenge Overview

The challenge requires solving 30 browser navigation puzzles in under 5 minutes, testing:
- Modal/popup dismissal
- Form input and submission
- Code extraction from page content
- Distractor avoidance (fake buttons)
- Dynamic content handling

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Main Agent Loop                       │
│  - Reads DOM structure (not vision - faster)            │
│  - Orchestrates sub-handlers                            │
│  - Tracks progress and metrics                          │
└─────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │Modal Handler │ │Code Extractor│ │Form Handler  │
    │- Cookie cons.│ │- Scroll codes│ │- Input codes │
    │- Alerts      │ │- Hidden codes│ │- Submit forms│
    │- Prizes      │ │- Timer codes │ │- Select opts │
    │- Newsletters │ │              │ │              │
    └──────────────┘ └──────────────┘ └──────────────┘
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Usage

```bash
# Run the agent
python agent.py

# Run with metrics output
python agent.py --metrics
```

## Metrics

The agent tracks:
- **Total time**: Time to complete all 30 challenges
- **Per-step time**: Time for each individual challenge
- **Token usage**: API tokens consumed (if using LLM)
- **Token cost**: Estimated cost

## Strategy

Based on analysis of the challenges:

1. **DOM-first approach**: Parse accessibility tree instead of screenshots for speed
2. **Pattern matching**: Identify common modal types and handle them systematically
3. **Code extraction**: Look for revealed codes in DOM (often after scroll/timer conditions)
4. **Parallel exploration**: Map action space quickly to find correct paths

## License

MIT
