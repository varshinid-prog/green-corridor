import traci


class SignalController:

    def __init__(self):
        # Only intersections where our ambulance needs priority.
        self.intersections = {
            "B1": {
                "link_index": 13,
                "incoming_edge": "A1B1",
                "outgoing_edge": "B1C1"
            },
            "C1": {
                "link_index": 7,
                "incoming_edge": "B1C1",
                "outgoing_edge": "C1C2"
            }
        }

        self.normal_program = "0"
        self.yellow_duration = 3
        self.all_red_duration = 2
        self.detection_distance = 80

        self.active_tls = None
        self.stage = "IDLE"
        self.stage_started_at = 0

    def start_preemption(self, tls_id, current_time):

        config = self.intersections[tls_id]

        # Read the current signal state.
        current_state = traci.trafficlight.getRedYellowGreenState(tls_id)

        # Convert green movements to yellow.
        yellow_state = ""

        for light in current_state:
            if light in ("G", "g"):
                yellow_state += "y"
            else:
                yellow_state += light

        self.active_tls = tls_id
        self.stage = "YELLOW"
        self.stage_started_at = current_time

        traci.trafficlight.setRedYellowGreenState(
            tls_id, yellow_state
        )

        print(f"\n[YELLOW] {tls_id}: clearing existing traffic")

    def restore_signal(self):

        tls_id = self.active_tls

        if tls_id is not None:
            traci.trafficlight.setProgram(
                tls_id, self.normal_program
            )

            print(f"[RESTORED] {tls_id}: normal signal program resumed")

        self.active_tls = None
        self.stage = "IDLE"

    def update(self, ambulance_id, current_time):

        # If no priority operation is active, look for an approaching signal.
        if self.stage == "IDLE":

            if ambulance_id not in traci.vehicle.getIDList():
                return

            next_tls = traci.vehicle.getNextTLS(ambulance_id)
            current_road = traci.vehicle.getRoadID(ambulance_id)

            for tls_info in next_tls:

                tls_id = tls_info[0]
                distance = tls_info[2]

                if tls_id not in self.intersections:
                    continue

                config = self.intersections[tls_id]

                # Only activate for the expected approach and movement.
                if (
                    current_road == config["incoming_edge"]
                    and distance <= self.detection_distance
                ):
                    self.start_preemption(tls_id, current_time)
                    break

            return

        tls_id = self.active_tls
        config = self.intersections[tls_id]

        elapsed = current_time - self.stage_started_at

        # Stage 1: hold yellow, then switch to all-red.
        if self.stage == "YELLOW":

            if elapsed >= self.yellow_duration:

                all_red_state = "r" * len(
                    traci.trafficlight.getRedYellowGreenState(tls_id)
                )

                traci.trafficlight.setRedYellowGreenState(
                    tls_id, all_red_state
                )

                self.stage = "ALL_RED"
                self.stage_started_at = current_time

                print(f"[ALL RED] {tls_id}: intersection clearance")

        # Stage 2: hold all-red, then grant ambulance priority.
        elif self.stage == "ALL_RED":

            if elapsed >= self.all_red_duration:

                green_state = ["r"] * len(
                    traci.trafficlight.getRedYellowGreenState(tls_id)
                )

                green_state[config["link_index"]] = "G"

                traci.trafficlight.setRedYellowGreenState(
                    tls_id, "".join(green_state)
                )

                self.stage = "EMERGENCY_GREEN"

                print(
                    f"[AMBULANCE GREEN] {tls_id}: "
                    f"movement {config['link_index']} has priority"
                )

        # Stage 3: keep priority until the ambulance exits the junction.
        elif self.stage == "EMERGENCY_GREEN":

            if ambulance_id not in traci.vehicle.getIDList():
                print("[FAILSAFE] Ambulance no longer in simulation")
                self.restore_signal()
                return

            current_road = traci.vehicle.getRoadID(ambulance_id)

            if current_road == config["outgoing_edge"]:
                print(f"[PASSED] Ambulance crossed {tls_id}")
                self.restore_signal()