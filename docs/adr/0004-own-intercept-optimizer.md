# 0004 Own moving-target intercept optimizer; external projects not integrated

Status: accepted, 2026-10-31

Evaluated: HALEM (MIT, Python, last release 2022; routes between fixed points through a flow field, no moving targets), windmar-demo (Apache-2.0; Copernicus account needed), ShipNetSim (C++/Qt, GPL-3.0), Plankton/LOTUSim (ROS2/Gazebo 3D, multi-GB, out of SRS scope). None fit a one-day build or the moving-target problem.

We implement a small pure-Python optimizer: RK2 drift prediction, bisection intercept with current-aided vessel motion, cubic power-law energy, and greedy mass/energy chaining of up to 3 targets, gated by a 2 km deviation threshold. It runs in the Spark streaming driver's foreachBatch. The fuel model follows ShipNetSim's resistance → power → fuel approach, simplified; credited in the presentation.
