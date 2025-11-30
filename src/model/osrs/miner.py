import time
import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
from model.osrs.jagex_account_bot import OSRSJagexAccountBot
from model.runelite_bot import BotStatus
from utilities.geometry import RuneLiteObject


class OSRSMiner(OSRSJagexAccountBot):
    def __init__(self):
        bot_title = "Miner (MLM + Regular)"
        description = (
            "Power mines ore or pay-dirt in Motherlode Mine.\n"
            "Tag ore veins PINK.\n"
            "For Motherlode Mine: tag the Hopper RED.\n"
            "Tag the Sack GREEN.\n"
            "Tag the Bank Chest BLUE.\n"
            "For upper level: Mark top of ladder cyan (0, 255, 255)\n"
            "and bottom of ladder purple (170, 0, 255)"
        )
        super().__init__(bot_title=bot_title, description=description, debug=False)

        # --------------------- DEFAULT OPTIONS ---------------------
        self.running_time = 60
        self.take_breaks = False
        self.skip_slots = []
        self.bank_minimap_direction = None
        self.collect_from_sack = True
        self.ore_action = "Deposit pay-dirt to hopper"
        self.ore_type = "Paydirt"
        self.upper_level = True
        self._paydirt_item_name = "Pay_dirt"
        self.on_upper_level = True
        self.hopper_deposits = 0

    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_checkbox_option("collect_from_sack", "Collect from sack?", [" "])
        self.options_builder.add_checkbox_option("upper_level", "Upper level?", [" "])
        self.options_builder.add_dropdown_option(
            "ore_action", "When inventory full:",
            ["Drop ore", "Deposit ore to bank", "Deposit pay-dirt to hopper"]
        )
        self.options_builder.add_dropdown_option(
            "ore_type", "Ore type (only for regular mining):",
            ["Iron", "Silver", "Coal", "Gold", "Paydirt"]
        )
        self.options_builder.add_dropdown_option(
            "bank_minimap_direction", "Bank direction (if off-screen):",
            ["None", "North", "South", "East", "West", "Northeast", "Northwest", "Southeast", "Southwest"]
        )

    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "collect_from_sack":
                self.collect_from_sack = options[option] != []
            elif option == "upper_level":
                self.upper_level = options[option] != []
            elif option == "ore_action":
                self.ore_action = options[option]
            elif option == "ore_type":
                self.ore_type = options[option]
            elif option == "bank_minimap_direction":
                self.bank_minimap_direction = None if options[option] == "None" else options[option].lower()
        self.log_msg(f"Running for {self.running_time} minutes | Action: {self.ore_action}")
        if self.collect_from_sack:
            self.log_msg("SACK = GREEN TAG → WILL BE COLLECTED AFTER HOPPER DEPOSIT")
        self.options_set = True

    # ===================================================================
    #                           MAIN LOOP
    # ===================================================================
    def main_loop(self):
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()
        time.sleep(1.0)

        start_time = time.time()
        end_time = self.running_time * 60
        failed_searches = 0

        while time.time() - start_time < end_time:
            print('info panel text: ', self.info_panel_text(color=clr.OFF_WHITE))
            if rd.random_chance(0.04) and self.take_breaks:
                self.take_break(max_seconds=45, fancy=True)

            # ================== FULL INVENTORY HANDLING ==================
            if self.is_inventory_full():
                print('inventory full')
                self.__handle_full_inventory()
                continue

            print('not full inventory')
            print('hopper deposits: ', self.hopper_deposits)
            print('should collect: ', self.collect_from_sack and self.hopper_deposits == 4)

            if self.collect_from_sack and self.hopper_deposits == 4:
                print('collecting from sack')
                self.__collect_from_sack_loop()

            print('in main loop, on upper level: ', self.on_upper_level)
            if self.upper_level and not self.on_upper_level:
                self.__climb_ladder(color=clr.PURPLE)
                self.hopper_deposits = 0
                continue

            # ================== FIND ORE VEIN (PINK) ==================
            if not (
                self.mouseover_text(contains="Ore vein", color=clr.OFF_GREEN) or
                self.mouseover_text(contains=self.ore_type, color=clr.OFF_GREEN) or
                self.mouseover_text(contains="Mine", color=clr.OFF_GREEN)
            ):
                if not self.move_mouse_to_nearest_item(clr.PINK, speed="fastest"):
                    failed_searches += 1
                    if failed_searches % 10 == 0:
                        self.log_msg("Searching for ore veins...")
                    if failed_searches > 80:
                        self.__logout("No ore veins found for too long.")
                    time.sleep(6.5)
                    continue
                failed_searches = 0

            # ================== CLICK ROCK ==================
            if not self.active_message("Mining"):
                self.mouse.click()
                tstart = time.time()
                while not self.active_message("Mining") and time.time() - tstart < 5.5:
                    time.sleep(0.5)

            # ================== WAIT WHILE MINING ==================
            hop_chance = 0.18
            wait_cycles = 0
            while self.active_message("Mining"):
                if rd.random_chance(hop_chance):
                    self.move_mouse_to_nearest_item(clr.PINK, next_nearest=True)
                    hop_chance /= 2
                time.sleep(4)
                wait_cycles += 1
                if wait_cycles > 40:
                    self.log_msg("Mining took too long — forcing continue")
                    break

            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.__logout("Script finished.")

    # ===================================================================
    #              HANDLE FULL INVENTORY
    # ===================================================================
    def __handle_full_inventory(self):
        paydirt_slot = self.get_item_slot(self._paydirt_item_name)
        print('paydirt slot', paydirt_slot)

        if paydirt_slot != -1:
            # Deposit pay-dirt to hopper
            print('depositing to hopper from full inventory')
            if self.__deposit_to_hopper():
                # After depositing to hopper, collect from sack if enabled
                print('deposited to hopper')
                
            else:
                time.sleep(3)
            return

        # No paydirt, deposit to bank or drop
        bank_obj = self.get_nearest_tag(clr.BLUE)
        if bank_obj:
            self.mouse.move_to(bank_obj.random_point(), mouseSpeed="fast")
            time.sleep(1.0)
            self.mouse.click()
            time.sleep(2.5)
            try:
                self.bank.deposit_inventory()
                self.log_msg("Deposited inventory → bank chest.")
            except Exception as e:
                self.log_msg(f"Failed to deposit inventory: {e}")
            try:
                self.bank.close()
            except Exception:
                pass
            time.sleep(1.0)
            return

        self.log_msg("No bank chest detected — dropping inventory.")
        self.drop_all(skip_slots=self.skip_slots)
        time.sleep(1.5)

    # ===================================================================
    #              COLLECT FROM SACK LOOP
    # ===================================================================
    def __collect_from_sack_loop(self):
        """
        Collects from sack and deposits to bank repeatedly until sack is empty.
        Loop: collect from sack -> deposit to bank -> (if green tag still exists) repeat
        """
        print('collecting from sack loop')
        while True:
            sack = self.get_nearest_tag(clr.GREEN)
            print('sack', sack)
            if not sack:
                # No green tag, sack is empty
                print('sack is empty')
                break

            print('in collect from sack loop, on upper level: ', self.on_upper_level)
            if self.upper_level and self.on_upper_level:
                self.__climb_ladder()
                continue
            
            # Collect from sack
            if not self.__collect_from_sack():
                # Failed to collect, break to avoid infinite loop
                print('failed to collect from sack')
                break
            
            # Deposit to bank
            if not self.deposit_to_bank(color=clr.BLUE):
                # Failed to deposit, break to avoid infinite loop
                print('failed to deposit to bank')
                break
            
            # Small delay before checking sack again
            time.sleep(1.0)

    # ===================================================================
    #                       HOPPER DEPOSIT
    # ===================================================================
    def __deposit_to_hopper(self) -> bool:
        hopper = self.get_nearest_tag(clr.RED)
        if not hopper:
            self.log_msg("Hopper not found — tag it RED!")
            return False
        self.mouse.move_to(hopper.random_point(), mouseSpeed="fast")
        time.sleep(0.8)
        if not self.mouseover_text(contains="Deposit", color=clr.OFF_WHITE):
            print('no deposit text found')
            return False
        self.mouse.click()
        print('clicked hopper, waiting for deposit to complete')
        # Player walks to hopper and deposits automatically
        # Wait for inventory to empty (deposit completes)
        deposit_timeout = 15  # seconds
        tstart = time.time()
        while self.is_inventory_full() and (time.time() - tstart) < deposit_timeout:
            time.sleep(0.5)
        if self.is_inventory_full():
            print('hopper deposit timed out')
            self.log_msg("Hopper deposit timed out")
            return False
        print('deposit completed, inventory is empty')
        self.log_msg("Deposited pay-dirt → hopper")
        time.sleep(2)  # Small delay after deposit completes
        # After depositing to hopper, collect from sack if enabled
        print(f'checking collect_from_sack: {self.collect_from_sack}')
        if self.collect_from_sack and self.hopper_deposits == 4:
            print('collecting from sack')
            self.__collect_from_sack_loop()
        else:
            print('collect_from_sack is False, skipping')
        print('returning True from __deposit_to_hopper')
        self.hopper_deposits += 1
        return True

    # ===================================================================
    #                   SACK COLLECTION (NOW LESS SPAMMY)
    # ===================================================================
    def __collect_from_sack(self) -> bool:
        if self.is_inventory_full():
            return False
        sack = self.get_nearest_tag(clr.GREEN)
        if not sack:
            return False
        self.mouse.move_to(sack.random_point(), mouseSpeed="fast")
        time.sleep(0.5)
        if not (self.mouseover_text(contains="Search", color=clr.OFF_WHITE) or
                self.mouseover_text(contains="Collect", color=clr.OFF_WHITE)):
            return False
        self.mouse.click()
        time.sleep(3)
        return True

    # ===================================================================
    #                    BANK DEPOSIT (BLUE CHEST)
    # ===================================================================
    def __open_bank_chest(self) -> bool:
        bank_obj = self.get_nearest_tag(clr.BLUE)
        if not bank_obj:
            self.log_msg("Could not find BLUE bank chest tag.")
            return False
        self.mouse.move_to(bank_obj.random_point(), mouseSpeed="fast")
        time.sleep(0.8)
        if not self.mouseover_text(contains="Use Bank chest", color=clr.OFF_WHITE):
            return False
        self.mouse.click()
        time.sleep(1.5)
        tstart = time.time()
        while time.time() - tstart < 6.0:
            try:
                if self.bank.is_open():
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def __deposit_to_bank(self) -> bool:
        if not self.__open_bank_chest():
            return False
        try:
            self.bank.deposit_inventory()
            time.sleep(1.5)
            self.log_msg("Deposited inventory → bank chest.")
        except Exception as e:
            self.log_msg(f"Exception while depositing: {e}")
            try:
                self.bank.close()
            except Exception:
                pass
            return False
        try:
            self.bank.close()
        except Exception:
            pass
        time.sleep(0.5)
        return True

    def __climb_ladder(self, color: clr.Color = clr.CYAN):
        if not self.upper_level:
            print("color purple")
            color = clr.PURPLE
        ladder = self.get_nearest_tag(color)
        if not ladder:
            print('ladder not found')
            return False
        self.mouse.move_to(ladder.random_point(), mouseSpeed="fast")
        time.sleep(0.8) # wait for mouseover text
        if not self.mouseover_text(contains="Climb", color=clr.OFF_WHITE):
            print('no climb text found')
            return False
        self.mouse.click()
        time.sleep(5)
        self.on_upper_level = not self.on_upper_level
        return True

    # ===================================================================
    #                          LOGOUT
    # ===================================================================
    def __logout(self, msg):
        self.log_msg(msg)
        self.logout(msg)
        self.set_status(BotStatus.STOPPED)