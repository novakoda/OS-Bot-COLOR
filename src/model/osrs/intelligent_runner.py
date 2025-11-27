"""
Intelligent Runner Bot - Uses ML/AI agent for better decision making
Relies solely on computer vision and RuneLite plugin tags:
- GREEN: Current click point
- YELLOW: All possible click points
"""
import time
from typing import TYPE_CHECKING

import utilities.color as clr
import utilities.random_util as rd
from model.osrs.intelligent_runner_agent import IntelligentRunnerAgent
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus

if TYPE_CHECKING:
    from model.osrs.intelligent_runner_agent import ObstacleInfo


class OSRSIntelligentRunner(OSRSJagexAccountBot):
    """
    Enhanced runner bot that uses an intelligent agent to make decisions
    about which obstacles to interact with, especially handling the mark of grace
    glitch scenario where both the mark and next obstacle are green.
    
    Uses RuneLite plugin that marks:
    - GREEN: Current click point (the one to click next)
    - YELLOW: All possible click points on the course
    """
    
    def __init__(self):
        bot_title = "Intelligent Runner"
        description = (
            "This bot runs the agility course using AI/ML to make intelligent decisions. "
            "It uses computer vision and RuneLite plugin tags (GREEN=current, YELLOW=possible). "
            "It can handle scenarios where marks of grace and obstacles both appear green."
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)
        self.running_time = 1
        self.take_breaks = False
        self.agent = None
        # Long-distance obstacle handling (e.g., Seers' Village return climb)
        self.long_travel_distance_threshold = 230.0
        self.long_travel_monitor_time = 15.0  # seconds to watch for progress
        self.long_travel_wait_duration = 14.0  # seconds to wait before re-clicking
        self.long_travel_cooldown_until = 0.0
        self.long_travel_target_info = None
        self.long_travel_last_log = 0.0
        
    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
    
    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' ' if self.take_breaks else ' not '}take breaks.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def _is_long_travel_obstacle(self, obstacle: 'ObstacleInfo') -> bool:
        """Detect obstacles that require long travel time before interaction completes."""
        if not obstacle or not obstacle.is_current_click_point:
            return False
        try:
            distance = float(obstacle.distance)
        except (TypeError, ValueError):
            return False
        return distance >= self.long_travel_distance_threshold

    def _start_long_travel_cooldown(self, obstacle: 'ObstacleInfo'):
        """Start cooldown timer after clicking a long-distance obstacle."""
        center = obstacle.obj.center()
        self.long_travel_target_info = {
            "action": (obstacle.action or "obstacle").lower(),
            "position": (center.x, center.y),
        }
        self.long_travel_cooldown_until = time.time() + self.long_travel_wait_duration
        self.long_travel_last_log = 0.0
        self.log_msg(
            f"Long-distance travel detected ({self.long_travel_target_info['action']}), waiting up to "
            f"{int(self.long_travel_wait_duration)}s for player to reach it."
        )

    def _reset_long_travel_cooldown(self):
        """Clear any active long-distance cooldown."""
        self.long_travel_cooldown_until = 0.0
        self.long_travel_target_info = None
        self.long_travel_last_log = 0.0

    def _is_in_long_travel_cooldown(self) -> bool:
        """Return True if we are currently waiting for a long-distance traversal to finish."""
        return self.long_travel_cooldown_until > 0 and time.time() < self.long_travel_cooldown_until

    def _log_long_travel_wait(self):
        """Throttled logging while we wait to reach a long-distance obstacle."""
        if time.time() - self.long_travel_last_log < 3:
            return
        remaining = max(0, int(self.long_travel_cooldown_until - time.time()))
        action = "obstacle"
        if self.long_travel_target_info and self.long_travel_target_info.get("action"):
            action = self.long_travel_target_info["action"]
        self.log_msg(f"Player still traveling toward {action}, waiting {remaining}s before re-clicking...")
        self.long_travel_last_log = time.time()
    
    def main_loop(self):
        """Main loop using intelligent agent with CV-only approach"""
        # Initialize the intelligent agent
        self.agent = IntelligentRunnerAgent(self)
        self.log_msg("Intelligent agent initialized. Using computer vision only.")
        self.log_msg("Looking for GREEN (current) and YELLOW (possible) click points...")
        
        self.logs = 0
        failed_searches = 0
        actions = ["Jump", "Climb", "Take", "Vault", "Cross", "Grab", "Leap", "Hurdle", "Balance", "Swing", "Teeth"]
        
        # Main loop
        start_time = time.time()
        end_time = self.running_time * 60
        last_action_time = time.time()
        consecutive_failures = 0
        self._reset_long_travel_cooldown()
        
        while time.time() - start_time < end_time:
            # 3% chance to take a break between tag searches
            if rd.random_chance(probability=0.03) and self.take_breaks:
                self.take_break(max_seconds=12, fancy=True)
            
            # Get current game state (CV only)
            game_state = self.agent.get_game_state()
            if self.long_travel_cooldown_until and time.time() >= self.long_travel_cooldown_until:
                self._reset_long_travel_cooldown()
            
            # Check if we're stuck
            if self.agent.check_if_stuck(game_state):
                recovery = self.agent.get_recovery_action(game_state)
                
                if recovery == "rotate_camera":
                    self.log_msg("Detected stuck - rotating camera to find click points")
                    if self.agent.rotate_camera_to_find_obstacles(max_rotations=4):
                        # Found obstacles after rotation, continue
                        continue
                    else:
                        # Still no obstacles, wait a bit
                        time.sleep(2)
                        consecutive_failures += 1
                        if consecutive_failures > 5:
                            self.log_msg("Too many consecutive failures, logging out.")
                            self.__logout("Bot appears to be stuck. Logging out.")
                        continue
                
                elif recovery == "rotate_camera_or_try_yellow":
                    self.log_msg("Detected stuck - trying yellow tags or rotating camera")
                    # First try yellow tags
                    obstacles = self.agent.detect_obstacles(actions)
                    yellow_obstacles = [obs for obs in obstacles if obs.is_possible_click_point and not obs.is_mark_of_grace]
                    if yellow_obstacles:
                        obstacle = self.agent._select_closest_obstacle(yellow_obstacles)
                        if obstacle:
                            self._interact_with_obstacle(
                                obstacle,
                                game_state,
                                is_long_travel=self._is_long_travel_obstacle(obstacle),
                            )
                            continue
                    # If no yellow tags, rotate camera
                    if self.agent.rotate_camera_to_find_obstacles(max_rotations=4):
                        continue
                    time.sleep(2)
                    consecutive_failures += 1
                    if consecutive_failures > 5:
                        self.log_msg("Too many consecutive failures, logging out.")
                        self.__logout("Bot appears to be stuck. Logging out.")
                    continue
                
                else:
                    self.log_msg("Detected stuck - waiting...")
                    time.sleep(2)
                    consecutive_failures += 1
                    if consecutive_failures > 5:
                        self.log_msg("Too many consecutive failures, logging out.")
                        self.__logout("Bot appears to be stuck. Logging out.")
                    continue
            
            # Detect all obstacles (green and yellow tags)
            obstacles = self.agent.detect_obstacles(actions)
            
            if not obstacles:
                failed_searches += 1
                if failed_searches % 10 == 0:
                    self.log_msg("Searching for click points (GREEN/YELLOW tags)...")
                
                # When running between laps or obstacles, tags may not be visible
                # Wait longer before taking action (especially after a recent successful interaction)
                if failed_searches > 30:
                    # Try rotating camera before giving up
                    self.log_msg("No click points found, rotating camera...")
                    if self.agent.rotate_camera_to_find_obstacles(max_rotations=2):
                        failed_searches = 0
                        continue
                
                # Only logout after a very long time (player might be running between laps)
                if failed_searches > 120:  # Increased from 60 to 120 seconds
                    self.__logout("No agility course found. Logging out.")
                
                # Wait a bit longer when no obstacles found (player might be running)
                time.sleep(1.5)  # Increased from 1 to 1.5 seconds
                continue
            
            failed_searches = 0  # Reset if we found obstacles
            
            # Use intelligent agent to select best obstacle
            selected_obstacle = self.agent.select_best_obstacle(obstacles, game_state)
            
            if not selected_obstacle:
                # No suitable obstacle found, try rotating camera
                self.log_msg("No suitable click point found, rotating camera...")
                if self.agent.rotate_camera_to_find_obstacles(max_rotations=2):
                    continue
                time.sleep(0.5)
                continue
            
            # Interact with the selected obstacle
            is_long_travel = self._is_long_travel_obstacle(selected_obstacle)
            if is_long_travel and self._is_in_long_travel_cooldown():
                self._log_long_travel_wait()
                time.sleep(1.2)
                continue
            success = self._interact_with_obstacle(selected_obstacle, game_state, is_long_travel=is_long_travel)
            
            # Record the result for learning
            self.agent.record_action_result(selected_obstacle, success, game_state)
            if is_long_travel:
                if success:
                    self._start_long_travel_cooldown(selected_obstacle)
                else:
                    self._reset_long_travel_cooldown()
            else:
                self._reset_long_travel_cooldown()
            
            if success:
                consecutive_failures = 0
                last_action_time = time.time()
            else:
                consecutive_failures += 1
                
                # If green tag interaction failed, try recovery strategies
                if selected_obstacle.is_current_click_point:
                    # Strategy 1: Try rotating camera to find new obstacles (might reveal next obstacle)
                    if consecutive_failures <= 2:
                        self.log_msg("Green tag unchanged, rotating camera to find next obstacle...")
                        if self.agent.rotate_camera_to_find_obstacles(max_rotations=2):
                            # Found new obstacles after rotation, re-detect and continue
                            time.sleep(1)
                            continue
                    
                    # Strategy 2: Try clicking the same green object again (maybe click didn't register)
                    if consecutive_failures == 1:
                        self.log_msg("Retrying same green object (click may not have registered)...")
                        time.sleep(1)
                        retry_success = self._interact_with_obstacle(
                            selected_obstacle,
                            game_state,
                            is_long_travel=self._is_long_travel_obstacle(selected_obstacle),
                        )
                        self.agent.record_action_result(selected_obstacle, retry_success, game_state)
                        if retry_success:
                            consecutive_failures = 0
                            last_action_time = time.time()
                            time.sleep(4)
                            self.update_progress((time.time() - start_time) / end_time)
                            continue
                    
                    # Strategy 3: Try yellow tags as fallback
                    if consecutive_failures <= 3:
                        self.log_msg("Green tag interaction failed, trying yellow tags as fallback...")
                        # Re-detect obstacles in case new ones appeared
                        current_obstacles = self.agent.detect_obstacles(actions)
                        yellow_obstacles = [obs for obs in current_obstacles if obs.is_possible_click_point and not obs.is_mark_of_grace]
                        if yellow_obstacles:
                            # Exclude recently clicked obstacles to avoid loops
                            yellow_obstacle = self.agent._select_closest_obstacle(yellow_obstacles, exclude_recent=True)
                            if yellow_obstacle:
                                self.log_msg(f"Trying yellow tag: {yellow_obstacle.action}")
                                success = self._interact_with_obstacle(
                                    yellow_obstacle,
                                    game_state,
                                    is_long_travel=self._is_long_travel_obstacle(yellow_obstacle),
                                )
                                self.agent.record_action_result(yellow_obstacle, success, game_state)
                                if success:
                                    consecutive_failures = 0
                                    last_action_time = time.time()
                                    time.sleep(4)
                                    self.update_progress((time.time() - start_time) / end_time)
                                    continue
                            else:
                                self.log_msg("All yellow tags were recently clicked, skipping fallback")
                
                if consecutive_failures > 10:
                    self.log_msg("Too many consecutive failures, logging out.")
                    self.__logout("Bot appears to be stuck. Logging out.")
            
            # Wait for action to complete
            time.sleep(4)
            
            self.update_progress((time.time() - start_time) / end_time)
        
        # Cleanup
        if self.agent:
            self.agent.cleanup()
        
        self.update_progress(1)
        self.__logout("Finished.")
    
    def _interact_with_obstacle(self, obstacle: 'ObstacleInfo', game_state, is_long_travel: bool = False) -> bool:
        """
        Interact with an obstacle and determine if it was successful.
        Handles long-distance obstacles (e.g., Seers' Village return climb) by
        monitoring for progress longer before treating the interaction as failed.
        Args:
            obstacle: The obstacle to interact with
            game_state: Current game state
            is_long_travel: True when the obstacle is far from the player and we expect
                            several seconds of movement before the click completes.
        Returns:
            True if interaction was successful, False otherwise
        """
        try:
            # Move mouse to obstacle (fast movement since we're already detecting)
            self.mouse.move_to(obstacle.obj.random_point(), mouseSpeed="fastest")
            time.sleep(0.15)  # Wait for mouseover text
            
            # Check for ladder/staircase (skip these)
            if self.mouseover_text(contains=["Ladder", "Staircase"], color=clr.OFF_GREEN):
                self.log_msg("Skipping ladder/staircase")
                return False
            
            # Detect the actual action from mouseover text
            actions = ["Jump", "Climb", "Take", "Vault", "Cross", "Grab", "Leap", "Hurdle", "Balance", "Swing", "Teeth"]
            mouseover_text = self.mouseover_text()
            detected_action = None
            
            for act in actions:
                if self.mouseover_text(contains=[act], color=clr.OFF_WHITE):
                    detected_action = act
                    break
            
            # Update obstacle action if we detected one
            if detected_action:
                obstacle.action = detected_action
            
            # Determine if this is a mark of grace
            mouseover_lower = str(mouseover_text).lower() if mouseover_text else ""
            obstacle.is_mark_of_grace = detected_action == "Take" and ("mark" in mouseover_lower or "grace" in mouseover_lower)
            
            # Verify we're hovering over a valid action
            if not detected_action and obstacle.action == "Click":
                # No action detected, but we'll try clicking anyway
                pass
            
            # Special handling for mark of grace
            if obstacle.is_mark_of_grace and obstacle.action == "Take":
                # Check if we're in a good state to take it
                if not game_state.is_idle:
                    self.log_msg("Cannot take mark of grace - player is not idle")
                    return False
                
                # Check if there are other obstacles nearby that we should prioritize
                all_obstacles = self.agent.detect_obstacles(["Jump", "Climb", "Vault", "Cross", "Grab", "Leap", "Hurdle", "Balance", "Swing"])
                non_mark_obstacles = [obs for obs in all_obstacles if not obs.is_mark_of_grace]
                
                if non_mark_obstacles:
                    # There are other obstacles - check learning data
                    scenario_key = f"{'green' if obstacle.is_current_click_point else 'yellow'}_mark_with_obstacle_{len(all_obstacles)}"
                    mark_failures = self.agent.learning_data["failed_actions"].get(scenario_key, 0)
                    if mark_failures > 2:
                        self.log_msg("Learned: Skipping mark of grace when obstacles are present")
                        return False
            
            # Store original obstacle bounds and action for comparison
            original_obstacle_center = obstacle.obj.center()
            original_action = detected_action if detected_action else obstacle.action
            
            # Click the obstacle
            self.mouse.click()
            
            # Wait and check multiple times to see if we actually progressed
            time.sleep(1.0)
            check_interval = 0.8
            max_checks = 3
            if is_long_travel:
                check_interval = 1.0
                monitor_window = max(self.long_travel_monitor_time - 1.0, check_interval * 3)
                max_checks = max(3, int(monitor_window / check_interval))
                self.log_msg(
                    f"Monitoring long-distance interaction for up to {int(self.long_travel_monitor_time)}s..."
                )
            
            # Check multiple times over a period to see if we're actually progressing
            for check_attempt in range(max_checks):
                time.sleep(check_interval)
                new_game_state = self.agent.get_game_state()
                
                # Check if green tag disappeared (strong indicator of progress)
                # This is especially true when completing an obstacle - player moves to next area
                if obstacle.is_current_click_point:
                    if not new_game_state.has_green_tag and game_state.has_green_tag:
                        self.log_msg(f"Successfully interacted with {obstacle.action} (green tag disappeared - likely progressed)")
                        return True
                    
                    # Also check if we have no tags at all but had them before
                    # This could mean we completed the obstacle and are running to next one
                    if not new_game_state.has_green_tag and not new_game_state.has_yellow_tags:
                        if game_state.has_green_tag or game_state.has_yellow_tags:
                            # Had tags before, now none - likely completed obstacle and running
                            self.log_msg(f"Successfully interacted with {obstacle.action} (tags disappeared - likely between obstacles/laps)")
                            return True
                
                # Check if we're still hovering over the same obstacle
                # Move mouse to where green tag is now (if it exists)
                if new_game_state.has_green_tag and new_game_state.green_tag_position:
                    # Get the new green object
                    green_objects = self.get_all_tagged_in_rect(self.win.game_view, clr.GREEN)
                    if green_objects:
                        new_green_obj = green_objects[0]
                        new_green_center = new_green_obj.center()
                        
                        # Check if new green tag is still within the original obstacle bounds
                        # (if it's far from the original, we likely progressed)
                        distance_from_original = (
                            abs(new_green_center.x - original_obstacle_center.x) +
                            abs(new_green_center.y - original_obstacle_center.y)
                        )
                        
                        # Get obstacle size to determine if we moved far enough
                        obstacle_width = obstacle.obj._width
                        obstacle_height = obstacle.obj._height
                        obstacle_size = max(obstacle_width, obstacle_height, 30)  # Minimum 30 pixels
                        
                        # Check if action text changed (different action = different obstacle)
                        self.mouse.move_to(new_green_obj.random_point(), mouseSpeed="fastest")
                        time.sleep(0.1)
                        new_action = None
                        for act in actions:
                            if self.mouseover_text(contains=[act], color=clr.OFF_WHITE):
                                new_action = act
                                break
                        
                        # If action changed, we're definitely on a different obstacle
                        if new_action and new_action != original_action:
                            self.log_msg(f"Successfully interacted with {obstacle.action} (action changed to {new_action})")
                            return True
                        
                        # If green tag moved significantly (more than 1.5x obstacle size), we likely progressed
                        if distance_from_original > obstacle_size * 1.5:
                            self.log_msg(f"Successfully interacted with {obstacle.action} (green tag moved far: {distance_from_original:.0f}px)")
                            return True
                        
                        # If green tag is still in similar position and same action, we might still be stuck
                        # But sometimes the tag doesn't update immediately even if we progressed
                        if distance_from_original < obstacle_size * 0.5 and new_action == original_action:
                            # Check if we can still interact with it from current position
                            # If we can't, we might have moved past it
                            if check_attempt == max_checks - 1:  # Last check
                                # Try to see if we can still interact with the same action
                                # If the action is no longer available, we might have progressed
                                can_still_interact = self.mouseover_text(contains=[original_action], color=clr.OFF_WHITE)
                                if not can_still_interact and original_action != "Click":
                                    # Action no longer available - might have progressed
                                    self.log_msg(f"Successfully interacted with {obstacle.action} (action no longer available - likely progressed)")
                                    return True
                                else:
                                    self.log_msg(f"Interaction with {obstacle.action} may have failed (still on same obstacle, moved only {distance_from_original:.0f}px)")
                                    return False
                            continue
                
                # For yellow tags, check if we now have a green tag or if yellow tags changed significantly
                if not obstacle.is_current_click_point:
                    if new_game_state.has_green_tag:
                        self.log_msg(f"Successfully interacted with {obstacle.action} (now have green tag)")
                        return True
                    if abs(new_game_state.num_yellow_tags - game_state.num_yellow_tags) > 1:
                        self.log_msg(f"Successfully interacted with {obstacle.action} (yellow tags changed significantly)")
                        return True
            
            # If we get here, we couldn't determine success clearly
            # Check one final time if green tag position changed significantly
            if obstacle.is_current_click_point and new_game_state.green_tag_position:
                if game_state.green_tag_position:
                    final_distance = (
                        abs(new_game_state.green_tag_position[0] - game_state.green_tag_position[0]) +
                        abs(new_game_state.green_tag_position[1] - game_state.green_tag_position[1])
                    )
                    if final_distance > 50:  # Moved more than 50 pixels
                        self.log_msg(f"Successfully interacted with {obstacle.action} (green tag moved significantly)")
                        return True
                    elif final_distance == 0:
                        # Green tag position hasn't changed at all - check if action is still available
                        # Move mouse to green tag and check
                        green_objects = self.get_all_tagged_in_rect(self.win.game_view, clr.GREEN)
                        if green_objects:
                            self.mouse.move_to(green_objects[0].random_point(), mouseSpeed="fastest")
                            time.sleep(0.1)
                            can_still_interact = self.mouseover_text(contains=[original_action], color=clr.OFF_WHITE)
                            if not can_still_interact and original_action != "Click":
                                # Action no longer available even though tag is in same position
                                # This might mean we progressed but tag hasn't updated
                                self.log_msg(f"Successfully interacted with {obstacle.action} (action unavailable despite same position - likely progressed)")
                                return True
            
            # Default to failure if we can't confirm progress
            self.log_msg(f"Interaction with {obstacle.action} may have failed (could not confirm progress)")
            return False
                
        except Exception as e:
            self.log_msg(f"Error interacting with obstacle: {e}")
            return False
    
    def __logout(self, msg):
        """Logout and cleanup"""
        self.log_msg(msg)
        if self.agent:
            self.agent.cleanup()
        self.logout()
        self.stop()
