"""
Intelligent Agent for Agility Course Runner Bot
Uses computer vision and learning to make better decisions
Relies on RuneLite plugin that marks:
- YELLOW: All possible click points on the course
- GREEN: Current click point
"""
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import utilities.color as clr
from utilities.geometry import RuneLiteObject


@dataclass
class ObstacleInfo:
    """Information about a detected obstacle"""
    obj: RuneLiteObject
    action: str  # "Jump", "Climb", "Take", etc.
    distance: float
    is_mark_of_grace: bool = False
    is_current_click_point: bool = False  # Is this the green (current) click point?
    is_possible_click_point: bool = False  # Is this a yellow (possible) click point?


@dataclass
class GameState:
    """Current game state from computer vision only"""
    has_green_tag: bool = False  # Current click point visible
    has_yellow_tags: bool = False  # Possible click points visible
    green_tag_position: Optional[Tuple[int, int]] = None
    num_yellow_tags: int = 0
    is_idle: bool = True  # Determined by checking if action text is present
    last_action_time: float = 0.0
    last_green_position: Optional[Tuple[int, int]] = None


class IntelligentRunnerAgent:
    """
    Intelligent agent that uses CV and learning
    to make better decisions about which obstacles to interact with
    Uses RuneLite plugin tags:
    - GREEN: Current click point (the one to click next)
    - YELLOW: All possible click points on the course
    """
    
    def __init__(self, bot_instance, learning_file: str = "runner_learning.json"):
        """
        Initialize the intelligent agent
        Args:
            bot_instance: The bot instance (for accessing CV methods)
            learning_file: Path to save/load learning data
        """
        self.bot = bot_instance
        self.learning_file = learning_file
        
        # Learning data: track successful/failed actions
        self.learning_data = self._load_learning_data()
        
        # Track recent actions to avoid getting stuck
        self.recent_actions = []  # List of (action, obstacle_type, success, timestamp)
        self.stuck_count = 0
        self.last_green_position = None
        self.position_stuck_threshold = 5  # Same position for 5 checks = stuck
        self.consecutive_same_position = 0
        
        # Track recently clicked obstacles to avoid clicking the same one repeatedly
        self.recently_clicked_positions = []  # List of (x, y) positions of recently clicked obstacles
        self.recent_click_timeout = 10.0  # Seconds to remember a clicked obstacle
        
    def _load_learning_data(self) -> Dict:
        """Load learning data from file"""
        if os.path.exists(self.learning_file):
            try:
                with open(self.learning_file, 'r') as f:
                    data = json.load(f)
                    # Convert back to defaultdict
                    data["successful_actions"] = defaultdict(int, data.get("successful_actions", {}))
                    data["failed_actions"] = defaultdict(int, data.get("failed_actions", {}))
                    return data
            except Exception as e:
                print(f"Error loading learning data: {e}")
        return {
            "successful_actions": defaultdict(int),
            "failed_actions": defaultdict(int),
            "mark_of_grace_patterns": [],
            "stuck_patterns": []
        }
    
    def _save_learning_data(self):
        """Save learning data to file"""
        try:
            # Convert defaultdict to regular dict for JSON serialization
            data = {
                "successful_actions": dict(self.learning_data["successful_actions"]),
                "failed_actions": dict(self.learning_data["failed_actions"]),
                "mark_of_grace_patterns": self.learning_data["mark_of_grace_patterns"],
                "stuck_patterns": self.learning_data["stuck_patterns"]
            }
            with open(self.learning_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving learning data: {e}")
    
    def get_game_state(self) -> GameState:
        """Get current game state from computer vision only"""
        try:
            # Get green tags (current click point)
            green_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.GREEN)
            has_green = len(green_objects) > 0
            
            # Get yellow tags (all possible click points) - also check DARK_YELLOW
            yellow_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.YELLOW)
            dark_yellow_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.DARK_YELLOW)
            yellow_objects = yellow_objects + dark_yellow_objects
            has_yellow = len(yellow_objects) > 0
            
            # Get position of green tag if exists
            green_position = None
            if green_objects:
                green_center = green_objects[0].center()
                green_position = (green_center.x, green_center.y)
            
            # Check if player is idle by looking for action text
            # If we see action text, player is likely doing something
            actions = ["Jump", "Climb", "Take", "Vault", "Cross", "Grab", "Leap", "Hurdle", "Balance", "Swing"]
            is_idle = not any(self.bot.mouseover_text(contains=[action], color=clr.OFF_WHITE) for action in actions)
            
            return GameState(
                has_green_tag=has_green,
                has_yellow_tags=has_yellow,
                green_tag_position=green_position,
                num_yellow_tags=len(yellow_objects),
                is_idle=is_idle,
                last_action_time=time.time(),
                last_green_position=self.last_green_position
            )
        except Exception as e:
            print(f"Error getting game state: {e}")
            return GameState()
    
    def detect_obstacles(self, actions: List[str]) -> List['ObstacleInfo']:
        """
        Detect all obstacles in the game view using yellow/green tag system
        Args:
            actions: List of valid actions to look for
        Returns:
            List of ObstacleInfo objects
        """
        obstacles = []
        
        # Get green tags (current click point - should be prioritized)
        green_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.GREEN)
        
        # Get yellow tags (all possible click points)
        yellow_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.YELLOW)
        
        # Process green tags first (these are the current click points)
        # Don't move mouse here - we'll detect action when we actually interact
        for obj in green_objects:
            obj.set_rectangle_reference(self.bot.win.game_view)
            
            # Default action - will be detected when we interact
            action = "Click"
            
            # Calculate distance from center
            distance = obj.distance_from_rect_center()
            
            # We can't determine if it's a mark of grace without mouseover, so default to False
            # Will be detected in _interact_with_obstacle
            is_mark = False
            
            obstacles.append(ObstacleInfo(
                obj=obj,
                action=action,
                distance=distance,
                is_mark_of_grace=is_mark,
                is_current_click_point=True,  # Green tags are current click points
                is_possible_click_point=False
            ))
        
        # Process yellow tags (possible click points)
        # Don't move mouse here - we'll detect action when we actually interact
        for obj in yellow_objects:
            obj.set_rectangle_reference(self.bot.win.game_view)
            
            # Default action - will be detected when we interact
            action = "Click"
            
            # Calculate distance from center
            distance = obj.distance_from_rect_center()
            
            # We can't determine if it's a mark of grace without mouseover, so default to False
            # Will be detected in _interact_with_obstacle
            is_mark = False
            
            obstacles.append(ObstacleInfo(
                obj=obj,
                action=action,
                distance=distance,
                is_mark_of_grace=is_mark,
                is_current_click_point=False,
                is_possible_click_point=True  # Yellow tags are possible click points
            ))
        
        return obstacles
    
    def select_best_obstacle(self, obstacles: List['ObstacleInfo'], game_state: GameState) -> Optional['ObstacleInfo']:
        """
        Select the best obstacle to interact with based on:
        - Green tags (current click point) are prioritized
        - Yellow tags (possible click points) are secondary
        - Distance
        - Action type
        - Whether it's a mark of grace
        - Learning data
        """
        if not obstacles:
            return None
        
        # Prioritize green tags (current click points) over yellow tags
        green_obstacles = [obs for obs in obstacles if obs.is_current_click_point]
        yellow_obstacles = [obs for obs in obstacles if obs.is_possible_click_point]
        
        # If we have green tags, use those (they're the current click points)
        if green_obstacles:
            # Filter out marks of grace if we've learned they're problematic
            non_mark_greens = [obs for obs in green_obstacles if not obs.is_mark_of_grace]
            mark_greens = [obs for obs in green_obstacles if obs.is_mark_of_grace]
            
            # If we have both marks and non-marks in green, check learning
            if mark_greens and non_mark_greens:
                scenario_key = f"green_mark_with_obstacle_{len(green_obstacles)}"
                mark_failures = self.learning_data["failed_actions"].get(scenario_key, 0)
                mark_successes = self.learning_data["successful_actions"].get(scenario_key, 0)
                
                # If marks have failed more often, prioritize non-marks
                if mark_failures > mark_successes and mark_failures > 2:
                    self.bot.log_msg("Learned: Skipping green mark of grace, prioritizing obstacle")
                    return self._select_closest_obstacle(non_mark_greens)
            
            # Prefer non-marks, but if only marks, use them
            if non_mark_greens:
                return self._select_closest_obstacle(non_mark_greens)
            elif mark_greens:
                # Check if mark is accessible (player should be idle)
                if game_state.is_idle:
                    return self._select_closest_obstacle(mark_greens)
                else:
                    # Player is moving, try yellow tags instead
                    if yellow_obstacles:
                        return self._select_closest_obstacle(yellow_obstacles)
                    return None
        
        # If no green tags, use yellow tags (possible click points)
        if yellow_obstacles:
            # Filter out marks if we've learned they're problematic
            non_mark_yellows = [obs for obs in yellow_obstacles if not obs.is_mark_of_grace]
            if non_mark_yellows:
                return self._select_closest_obstacle(non_mark_yellows)
            else:
                # Only marks available, use them if player is idle
                if game_state.is_idle:
                    return self._select_closest_obstacle(yellow_obstacles)
        
        return None
    
    def _was_recently_clicked(self, obstacle: 'ObstacleInfo', threshold: int = 30) -> bool:
        """
        Check if an obstacle was recently clicked
        Args:
            obstacle: The obstacle to check
            threshold: Pixel distance threshold to consider it the same obstacle
        Returns:
            True if this obstacle was recently clicked
        """
        center = obstacle.obj.center()
        obstacle_pos = (center.x, center.y)
        
        for clicked in self.recently_clicked_positions:
            clicked_pos = clicked["position"]
            # Calculate distance
            distance = (
                abs(obstacle_pos[0] - clicked_pos[0]) +
                abs(obstacle_pos[1] - clicked_pos[1])
            )
            if distance < threshold:
                return True
        return False
    
    def _select_closest_obstacle(self, obstacles: List['ObstacleInfo'], exclude_recent: bool = False) -> Optional['ObstacleInfo']:
        """
        Select the closest obstacle from a list
        Args:
            obstacles: List of obstacles to choose from
            exclude_recent: If True, exclude recently clicked obstacles
        Returns:
            The closest obstacle, or None if all are excluded
        """
        if not obstacles:
            return None
        
        # Filter out recently clicked obstacles if requested
        if exclude_recent:
            obstacles = [obs for obs in obstacles if not self._was_recently_clicked(obs)]
            if not obstacles:
                return None
        
        return min(obstacles, key=lambda obs: obs.distance)
    
    def record_action_result(self, obstacle: 'ObstacleInfo', success: bool, game_state: GameState):
        """
        Record the result of an action for learning
        Args:
            obstacle: The obstacle that was interacted with
            success: Whether the action was successful
            game_state: Game state at the time of action
        """
        # Create a key for this action type
        tag_type = "green" if obstacle.is_current_click_point else "yellow"
        action_key = f"{tag_type}_{obstacle.action}_{'mark' if obstacle.is_mark_of_grace else 'obstacle'}"
        
        if success:
            self.learning_data["successful_actions"][action_key] += 1
        else:
            self.learning_data["failed_actions"][action_key] += 1
        
        # Track mark of grace patterns
        if obstacle.is_mark_of_grace:
            pattern = {
                "timestamp": time.time(),
                "success": success,
                "tag_type": tag_type,
                "is_idle": game_state.is_idle,
                "num_yellow_tags": game_state.num_yellow_tags,
                "has_green_tag": game_state.has_green_tag
            }
            self.learning_data["mark_of_grace_patterns"].append(pattern)
            # Keep only last 100 patterns
            if len(self.learning_data["mark_of_grace_patterns"]) > 100:
                self.learning_data["mark_of_grace_patterns"] = \
                    self.learning_data["mark_of_grace_patterns"][-100:]
        
        # Track recent actions
        self.recent_actions.append({
            "action": obstacle.action,
            "is_mark": obstacle.is_mark_of_grace,
            "tag_type": tag_type,
            "success": success,
            "timestamp": time.time()
        })
        # Keep only last 20 actions
        if len(self.recent_actions) > 20:
            self.recent_actions = self.recent_actions[-20:]
        
        # Track clicked obstacle position to avoid clicking same one repeatedly
        if success:
            center = obstacle.obj.center()
            self.recently_clicked_positions.append({
                "position": (center.x, center.y),
                "timestamp": time.time()
            })
            # Clean up old positions (older than timeout)
            current_time = time.time()
            self.recently_clicked_positions = [
                pos for pos in self.recently_clicked_positions
                if current_time - pos["timestamp"] < self.recent_click_timeout
            ]
        
        # Save learning data periodically
        if len(self.recent_actions) % 5 == 0:
            self._save_learning_data()
    
    def check_if_stuck(self, game_state: GameState) -> bool:
        """
        Check if the bot is stuck by monitoring green tag position
        Returns:
            True if stuck, False otherwise
        """
        current_pos = game_state.green_tag_position
        
        if current_pos is None:
            # No green tag visible - might be stuck or between obstacles
            self.consecutive_same_position += 1
            if self.consecutive_same_position >= 3:
                return True
            return False
        
        if self.last_green_position is None:
            self.last_green_position = current_pos
            self.consecutive_same_position = 0
            return False
        
        # Check if position changed (within a small threshold for movement)
        position_threshold = 10  # pixels
        pos_diff = (
            abs(current_pos[0] - self.last_green_position[0]) +
            abs(current_pos[1] - self.last_green_position[1])
        )
        
        if pos_diff < position_threshold:
            # Position hasn't changed much
            self.consecutive_same_position += 1
        else:
            # Position changed
            self.consecutive_same_position = 0
            self.last_green_position = current_pos
        
        if self.consecutive_same_position >= self.position_stuck_threshold:
            # Record stuck pattern
            pattern = {
                "timestamp": time.time(),
                "position": current_pos,
                "recent_actions": self.recent_actions[-5:],
                "num_yellow_tags": game_state.num_yellow_tags,
                "has_green_tag": game_state.has_green_tag
            }
            self.learning_data["stuck_patterns"].append(pattern)
            if len(self.learning_data["stuck_patterns"]) > 50:
                self.learning_data["stuck_patterns"] = \
                    self.learning_data["stuck_patterns"][-50:]
            
            return True
        
        return False
    
    def get_recovery_action(self, game_state: GameState) -> Optional[str]:
        """
        Get a recovery action if stuck
        Returns:
            Recovery action suggestion or None
        """
        if not self.check_if_stuck(game_state):
            return None
        
        # Recovery strategies:
        # 1. Rotate camera to find more click points
        # 2. Try yellow tags if green tag is stuck
        # 3. Wait and retry
        
        if self.recent_actions:
            last_action = self.recent_actions[-1]
            if last_action["is_mark"] and not last_action["success"]:
                # We tried to take a mark and failed - try yellow tags or rotate camera
                return "rotate_camera_or_try_yellow"
        
        # Default: rotate camera to find new click points
        return "rotate_camera"
    
    def rotate_camera_to_find_obstacles(self, max_rotations: int = 4) -> bool:
        """
        Rotate camera to find obstacles when stuck
        Args:
            max_rotations: Maximum number of 90-degree rotations to try
        Returns:
            True if obstacles found after rotation, False otherwise
        """
        rotation_angle = 90  # Rotate 90 degrees each time
        
        for i in range(max_rotations):
            self.bot.log_msg(f"Rotating camera to find click points... ({i+1}/{max_rotations})")
            self.bot.move_camera(horizontal=rotation_angle)
            time.sleep(0.8)  # Wait for camera to settle and tags to update
            
            # Check if we now have green or yellow tags
            green_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.GREEN)
            yellow_objects = self.bot.get_all_tagged_in_rect(self.bot.win.game_view, clr.YELLOW)
            
            if green_objects or yellow_objects:
                self.bot.log_msg(f"Found click points after rotation!")
                # Reset stuck counter
                self.consecutive_same_position = 0
                self.last_green_position = None
                return True
        
        return False
    
    def cleanup(self):
        """Cleanup and save learning data"""
        self._save_learning_data()
