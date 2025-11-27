# Intelligent Runner Bot

## Overview

The Intelligent Runner Bot is an AI/ML-enhanced version of the agility course runner bot that uses:
- **Computer Vision Only**: No API dependencies - uses existing color detection and OCR methods
- **RuneLite Plugin Tags**: 
  - **GREEN**: Current click point (the one to click next)
  - **YELLOW**: All possible click points on the course
- **Machine Learning**: Learns from successful/failed actions to make better decisions
- **Intelligent Decision Making**: Handles edge cases like the mark of grace glitch
- **Camera Rotation**: Automatically rotates camera when stuck to find new click points

## Key Features

### 1. Mark of Grace Glitch Handling
The bot specifically addresses the issue where:
- A mark of grace spawns and appears green
- The next jumpable obstacle also appears green
- The bot gets stuck trying to "Take" the mark when it's not accessible yet

**Solution**: The intelligent agent:
- Detects when both a mark of grace and obstacle are present (both green)
- Prioritizes GREEN tags (current click points) over YELLOW tags (possible click points)
- Checks if player is idle (via CV - no action text visible)
- Learns from failed attempts to prioritize obstacles over marks in certain scenarios
- Skips marks when the player is not idle

### 2. Yellow/Green Tag System
The bot uses the RuneLite agility plugin that marks:
- **GREEN tags**: Current click point - these are prioritized
- **YELLOW tags**: All possible click points - used as fallback or when green is not available

**Decision Logic**:
1. Always prioritize GREEN tags (current click point)
2. If GREEN tag is a mark of grace and player is not idle, try YELLOW tags
3. If no GREEN tags, use YELLOW tags
4. If stuck, rotate camera to find new tags

### 3. Learning System
The bot learns from experience:
- Tracks successful vs failed actions
- Remembers patterns (e.g., "green mark of grace with obstacle present")
- Saves learning data to `runner_learning.json`
- Uses learned patterns to make better decisions
- Persists learning between sessions

### 4. Stuck Detection & Recovery
The bot can detect when it's stuck:
- Monitors GREEN tag position changes
- Detects when position hasn't changed for multiple iterations
- Implements recovery strategies:
  - **Rotate Camera**: Rotates camera 90° increments to find new click points
  - **Try Yellow Tags**: If green tag is stuck, tries yellow tags
  - **Wait and Retry**: Gives time for game state to update

### 5. Computer Vision Only
Uses only computer vision - no API dependencies:
- **Color Detection**: Detects GREEN and YELLOW tags
- **OCR**: Reads mouseover text for action detection
- **Position Tracking**: Monitors tag positions to detect movement
- **Idle Detection**: Checks for action text to determine if player is idle

## Usage

### Prerequisites
1. **RuneLite Plugin**: Ensure you have the agility course plugin enabled that marks:
   - GREEN: Current click point
   - YELLOW: All possible click points
2. **RuneLite Settings**: Configure the plugin to use these colors

### Basic Usage
1. Select "Intelligent Runner" from the bot list
2. Configure options:
   - Running time (minutes)
   - Take breaks (optional)
3. Start the bot

### Learning Data
The bot saves learning data to `runner_learning.json` in the project root. This file contains:
- Successful action patterns
- Failed action patterns
- Mark of grace interaction patterns
- Stuck scenario patterns

You can delete this file to reset learning, or let it accumulate for better performance over time.

## How It Works

### Decision Flow
1. **Detect Tags**: Uses CV to find all GREEN and YELLOW tagged objects
2. **Extract Information**: For each tag, determines:
   - Action type (Jump, Climb, Take, etc.)
   - Distance from player
   - Whether it's a mark of grace
   - Whether it's a current (green) or possible (yellow) click point
3. **Select Best Obstacle**: Uses intelligent agent to select:
   - Prioritizes GREEN tags over YELLOW tags
   - Considers distance
   - Considers action type
   - Considers learning data
   - Considers current game state (idle/moving)
4. **Interact**: Attempts to interact with selected obstacle
5. **Verify Success**: Checks if tag position changed (indicates movement)
6. **Learn**: Records success/failure for future decisions

### Mark of Grace Logic
When a mark of grace is detected:
1. Check if it's a GREEN tag (current click point) or YELLOW tag (possible click point)
2. Check if player is idle (no action text visible)
3. Check if there are other obstacles present
4. Check learning data for this scenario
5. If learned that marks fail in this scenario, prioritize obstacles
6. If player is not idle, skip mark and try yellow tags or wait

### Stuck Recovery
When stuck is detected:
1. **Rotate Camera**: Rotates camera 90° at a time (up to 4 rotations)
2. **Check for Tags**: After each rotation, checks for new GREEN/YELLOW tags
3. **Try Yellow Tags**: If green tag is stuck, tries yellow tags
4. **Wait**: If no tags found, waits and retries

## Technical Details

### Files
- `intelligent_runner.py`: Main bot class
- `intelligent_runner_agent.py`: AI/ML agent with decision-making logic
- `runner_learning.json`: Persistent learning data (auto-generated)

### Dependencies
- Existing bot infrastructure (Bot, RuneLiteBot, etc.)
- Computer vision utilities (color detection, OCR)
- **NO API dependencies** - works entirely with CV

### Color System
- **GREEN (clr.GREEN)**: Current click point - highest priority
- **YELLOW (clr.YELLOW)**: Possible click points - secondary priority
- Both colors are detected using existing `get_all_tagged_in_rect()` method

### Extending the Agent
To add more intelligence:
1. Add new patterns to track in `record_action_result()`
2. Add new decision factors in `select_best_obstacle()`
3. Add new recovery strategies in `get_recovery_action()`
4. Enhance stuck detection in `check_if_stuck()`

## Troubleshooting

### Bot Gets Stuck
- The bot should detect this automatically and rotate camera
- Check `runner_learning.json` for stuck patterns
- Delete learning file to reset if needed
- Ensure RuneLite plugin is marking tags correctly

### Mark of Grace Issues
- The bot learns to handle this automatically
- If issues persist, check that tags are being detected
- Verify that GREEN tags are showing current click point
- Check that YELLOW tags are showing possible click points

### No Tags Found
- Bot will rotate camera automatically
- Check RuneLite plugin settings
- Ensure plugin is enabled and configured correctly
- Verify tag colors match (GREEN and YELLOW)

### Performance
- Learning improves over time
- First few runs may have more failures as it learns
- Learning data persists between sessions
- Camera rotation may slow down progress but prevents getting stuck

## Future Enhancements

Potential improvements:
1. Better pattern recognition for obstacle types
2. More sophisticated stuck detection
3. Adaptive camera rotation strategies
4. Enhanced learning algorithms
5. Visual pattern recognition for different course layouts
