# Software Requirements Specification (SRS)
## Smart Ocean Waste Management & Route Optimizer

### 1. Introduction
**1.1 Purpose**
This document outlines the software requirements for a cloud-based simulation prototype of a Smart Waste Management & Route Optimizer designed for ocean plastic cleanup. It defines the architectural, functional, and non-functional specifications necessary to build a Big Data-driven pipeline capable of ingesting marine telemetry and calculating dynamically optimized cleanup routes.

**1.2 Scope**
The system focuses on single-vessel dynamic route planning. It utilizes synthetic IoT telemetry and public marine datasets (e.g., Copernicus, NOAA) to simulate real-world conditions. The core objective is to maximize debris collection per unit of vessel energy by anticipating ocean drift paths. Fleet orchestration and physical hardware integration are out of scope for this initial prototype phase.

---

### 2. System Architecture
**2.1 High-Level Processing Paradigm**
The system implements a hybrid Lambda architecture to handle both high-velocity streaming data and large-scale batch processing:
* **Speed Layer (Stream):** Apache Spark Structured Streaming processes continuous vessel telemetry for immediate state updates, micro-batch anomaly detection, and alert generation. It handles out-of-order events utilizing event-time watermarking.
* **Batch Layer:** PySpark offline ETL jobs process heavy, multidimensional oceanographic datasets to build historical and near-future spatial drift grids.

**2.2 Ingestion & Message Broker**
Apache Kafka serves as the distributed ingestion backbone. It decouples high-throughput synthetic IoT streams (simulated edge devices) and external data polling mechanisms from the downstream analytics engines. 

**2.3 Storage & Data Lakehouse**
* **Dual-Write Storage Pipeline:** Spark Streaming executes a dual-write mechanism. It simultaneously performs UPSERT operations to the operational database for low-latency live state, while appending immutable historical telemetry ticks directly into the analytical data lake.
* **Analytical Storage:** A data lake (MinIO/S3) utilizing Apache Iceberg or Parquet formats stores raw sensor logs, processed current grids, and historical metrics for scalable analytics.
* **Operational Storage:** A PostgreSQL database enriched with the PostGIS extension serves as the low-latency operational data store, housing active vessel states and calculated route geometries for frontend querying.

---

### 3. Functional Requirements
**3.1 IoT Telemetry Ingestion (Edge to Cloud)**
* The system must expose an ingestion endpoint to receive lightweight JSON payloads from simulated edge devices.
* Telemetry payloads must include calculated debris density (via simulated computer vision summaries), GPS coordinates, vessel speed, fuel/battery metrics, heading, and strict event timestamps.
* **Offline Queuing:** Simulated vessels must buffer telemetry locally during connectivity drops and flush queued payloads to Kafka upon reconnection.
* The ingestion layer must publish these payloads to dedicated Kafka topics partitioned by vessel ID and geographic zone.

**3.2 Oceanographic Data Pipeline**
* The batch processing layer must fetch global surface current estimates (e.g., NetCDF or GRIB format) from public APIs on a scheduled basis.
* PySpark jobs must parse the multidimensional scientific arrays, extracting velocity vectors ($u$ and $v$ components).
* The pipeline must interpolate these vectors onto a standardized spatial grid and write the output as spatio-temporally partitioned Parquet/Iceberg tables.

**3.3 Dynamic Route Optimization Engine**
* The pathfinding engine must query the partitioned ocean current tables and the active vessel state from PostGIS.
* The system must calculate the most energy-efficient intercept paths to high-density debris zones by factoring in the hydrodynamic drift of the waste.
* **Threshold-Based Recalculation:** The engine evaluates drift against the active route on a micro-batch cycle. It will only trigger computationally heavy route recalculations if the spatial deviation exceeds a predefined threshold limit.
* The engine must output a sequence of navigational waypoints and write the resulting route geometries back to PostGIS.

**3.4 State Management & API**
* The system must maintain a real-time "digital twin" of the cleaning vessel's state (location, fuel, capacity) in PostGIS.
* A RESTful API must be provided to expose vessel states, current trajectories, and historical cleanup metrics to the frontend.

---

### 4. Non-Functional Requirements
**4.1 Performance & Scalability**
* The Kafka broker must be configured to handle burst ingestion of telemetry without data loss, supporting horizontal scaling of partitions.
* Spark processing jobs must utilize distributed memory processing to ensure route recalculations complete within a defined SLA (e.g., under 60 seconds for a local grid area).

**4.2 Reliability & Fault Tolerance**
* The Kafka and Spark clusters must run in containerized environments (Docker Compose for local development) to ensure parity between local prototyping and eventual cloud deployments.
* Streaming jobs must implement checkpointing to recover gracefully from node failures without dropping telemetry events.

**4.3 Data Portability**
* Adherence to open-source standards (Python, PostgreSQL, Kafka, Spark, Parquet) must be strictly maintained to prevent cloud vendor lock-in, ensuring seamless migration between AWS, GCP, or bare-metal Linux servers.

---

### 5. UI/UX & Frontend Requirements
**5.1 Role-Based Access & Layout Architecture**
* **Admin Dashboard:** A multi-tabbed interface designed for oversight without information density issues.
  * **Map Tab:** A dedicated full-screen view for the live geospatial canvas, allowing admins to monitor vessel locations and ocean conditions.
  * **Metrics Tab:** A separate view for real-time system health, fuel monitoring, and operational statistics.
  * **Analytics Tab:** A dedicated view for historical reporting and performance queries.
* **Cleaner/Operator Dashboard:** A focused, operational interface providing the crew with immediate local telemetry, active intercept routes, and actionable prompts (e.g., "Accept Route Override").

**5.2 Geospatial Rendering (The Live Map)**
* **2D Flow Visualization:** The map will utilize a 2D canvas-based particle animation system (e.g., Leaflet or OpenLayers with a velocity overlay) to render flowing ocean currents, visually matching the style of `earth.nullschool.net` without the overhead of 3D WebGL.
* **Layer Controls:** The UI must include toggle switches to independently display or hide current particles, debris density heatmaps, and historical vessel wakes.

**5.3 State Synchronization**
* **WebSockets:** Drive the live operational views, ensuring minimal latency for live vessel tracking, active route recalculations, and critical alerts.
* **REST API:** Handles heavy historical data fetching for the analytics and reporting tabs.

**5.4 Operator Interaction (Human-in-the-Loop)**
* The system supports a Human-in-the-Loop workflow. Operators receive AI-generated routes as actionable prompts and can Accept, Reject, or Modify them based on real-world conditions.
* **Fail-Safe Loiter Default:** If an operator ignores an actionable prompt for a route change or a timeout is reached, the vessel automatically defaults to holding its current safe trajectory or entering a low-energy loiter pattern until manual intervention occurs.

**5.5 Tech Stack & Device Targeting**
* **Framework & Styling:** React.js paired with shadcn/ui and Tailwind CSS, utilizing a default Dark Mode theme suited for maritime environments.
* **Charting:** Recharts for rendering lightweight time-series graphs (e.g., Debris Collected vs. Fuel Consumed).
* **Viewport Strategy:** The UI is strictly targeted for desktop and landscape tablet displays (1080p+). Mobile phone responsiveness is explicitly excluded to prioritize data-rich layouts.