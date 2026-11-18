QUESTION

Can OCR and rule-based parsing reliably extract coordinate schedules from scanned Mzuzu City cadastral survey plans and auto-generate GIS-ready polygon files, within the Survey Department's 0.025 m accuracy tolerance?

WHY IT MATTERS

Coordinates on paper survey plans are currently transcribed into GIS software by hand, which is slow and open to transcription error. A tool that reads a scanned plan and produces a ready-to-use GeoPackage directly would save time and reduce mistakes on cadastral boundaries, and could plug into QGIS.

DATA I NEED

Sample scanned cadastral survey plans for Mzuzu City, with printed coordinate schedules

Local coordinate transformation parameters for Mzuzu City (Arc 1950 to WGS84, UTM zone 36S)

A set of verified beacon coordinates for the same sample plans, to check my extracted values against

WHERE EACH ONE COMES FROM

Sample plans — Department of Surveys, Mzuzu office, released for academic use. Already obtained. No public download link — institutional access only.

Transformation parameters — Department of Surveys, Mzuzu office. To be collected in person this coming week. No public download link.

Verified beacon coordinates — Department of Surveys records for the same plans, requested alongside them, used purely to check accuracy.

WHAT TO BE BUILT

GIS and Automated System that takes a scanned cadastral plan as input, use OCR to read its printed coordinate schedule, validate the values, assign the correct coordinate system, and output a GeoPackage containing the plan's boundary as a polygon checked against the verified beacon coordinates for accuracy.
