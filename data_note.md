# Data Notes

## 1. Data Source

The main data source for this project is the **Department of Surveys, Ministry of Lands, Mzuzu Office**. The project relies on institutional cadastral survey information rather than a publicly downloadable dataset, so access and timing depend on the Survey Department's data-release process.

---

## 2. Dataset 1 — Scanned Cadastral Survey Plans

- **Description:** Scanned cadastral survey plans for Mzuzu City, containing printed coordinate schedules. These plans are the starting point of the proposed system.
- **Source:** Department of Surveys, Ministry of Lands, Mzuzu Office.
- **Data type:** Scanned images, treated as image-based input from which text and numbers must be extracted.
- **Access:** Institutional (not a public download).
- **Intended use:** Test image preprocessing and OCR; extract and validate coordinate schedules; feed results into the GIS workflow.
- **Current status:** Acquisition in progress through the Survey Department.
- **Data quality to check once available:** scan quality, resolution, legibility, orientation, distortion, missing/damaged areas, coordinate precision and formatting consistency, handwritten vs. printed text, and overall OCR readiness.

---

## 3. Dataset 2 — Coordinate Transformation Parameters

- **Description:** Local transformation parameters needed to convert cadastral coordinates into the GIS reference system: **Arc 1950 → WGS84, UTM Zone 36S** (per the project brief).
- **Source:** Department of Surveys, Ministry of Lands, Mzuzu Office.
- **Data type:** Coordinate transformation parameters (exact format to be recorded once supplied).
- **Public availability:** None — institutional only.
- **Intended use:** Correctly transform/reference extracted coordinates before generating GIS features.
- **Current status:** Pending institutional acquisition; will be documented once received and verified.

---

## 4. Dataset 3 — Verified Beacon Coordinates

- **Description:** Verified beacon coordinates for the sample cadastral plans, used as reference data to assess extraction accuracy.
- **Source:** Department of Surveys records for the same cadastral plans.
- **Data type:** Survey coordinate data for cadastral beacons.
- **Intended use:** Compare automated-system-extracted coordinates against verified survey coordinates to evaluate positional accuracy of the extraction/transformation workflow.
- **Current status:** Requested through the institutional data-access process; will be documented on receipt.
