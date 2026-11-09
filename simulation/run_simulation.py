import traci
from signal_controller import SignalController

sumo_command = [
    "sumo",
    "-n", "network.net.xml",
    "-r", "traffic.rou.xml,ambulance.rou.xml",
    "--step-length", "1"
]

traci.start(sumo_command)
signal_controller = SignalController()

print("\n===================================")
print("       GREEN CORRIDOR SYSTEM")
print("===================================\n")

ambulance_id = "AMBULANCE_01"

try:
    while traci.simulation.getMinExpectedNumber() > 0:

        traci.simulationStep()

        current_time = traci.simulation.getTime()

        signal_controller.update(
            ambulance_id,
            current_time
)

        current_time = traci.simulation.getTime()

        # Check whether ambulance is in the simulation
        if ambulance_id in traci.vehicle.getIDList():

            road = traci.vehicle.getRoadID(ambulance_id)
            speed = traci.vehicle.getSpeed(ambulance_id)
            position = traci.vehicle.getPosition(ambulance_id)
            distance = traci.vehicle.getDistance(ambulance_id)

            if int(current_time) % 5 == 0:
                print(f"Time: {current_time:.0f}s")
                print(f"Ambulance road: {road}")
                print(f"Speed: {speed:.2f} m/s")
                print(f"Position: {position}")
                print(f"Distance travelled: {distance:.2f} m")
                print("-----------------------------------")

        else:
            if current_time < 2:
                print("Waiting for ambulance to enter simulation...")

finally:
    traci.close()

print("\nSimulation completed!")
