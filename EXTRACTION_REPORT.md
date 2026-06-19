# OCC Hub Extraction Report

**Source:** `OCCHUB_Drawio_File_V1.drawio`  
**Generated:** 2026-06-19T05:29:23.990897+00:00  

## Per-group counts

| Group | Count |
|-------|------:|
| internal | 337 |
| external | 11 |
| jobs | 7 |
| kafka_producer | 40 |
| kafka_consumer | 18 |
| redis | 1 |
| shared_path | 2 |
| sp | 26 |
| ms | 11 |
| mongo | 1 |
| aims | 1 |
| uncategorized | 0 |
| apps (floating) | 22 |
| microservices | 11 |

## Health summary

| Group | ok | warn | down |
|-------|---:|-----:|-----:|
| internal | 337 | 0 | 0 |
| external | 11 | 0 | 0 |
| jobs | 7 | 0 | 0 |
| kafka_producer | 13 | 27 | 0 |
| kafka_consumer | 18 | 0 | 0 |
| redis | 1 | 0 | 0 |
| shared_path | 2 | 0 | 0 |
| sp | 26 | 0 | 0 |
| ms | 11 | 0 | 0 |
| mongo | 1 | 0 | 0 |
| aims | 1 | 0 | 0 |

**leaf_cells_seen:** 611  
**names_extracted:** 477  
**sum(groups)+apps:** 477  
**skipped cells:** 95  

## Spatial frame → group mapping

| Frame (draw.io umlFrame) | Items spatially inside | Primary group |
|--------------------------|------------------------:|---------------|
| Cron Job | 15 | jobs |
| External Services | 23 | external |
| Internal endpoints | 3 | internal |
| Kafka Consumer | 6 | kafka_consumer |
| Kafka Producer | 2 | kafka_producer |
| Micro services | 23 | ms → microservices[] |
| Shared Path | 5 | shared_path |

## microservices

- occhub-admin-ms
- occhub-flight-ms
- occhub-crew-ms
- occhub-dispatch-ms
- occhub-weather-ms
- occhub-externalcomunication-ms
- occhub-crewresoucedashboard-ms
- occhub-rosterautomation-ms
- occhub-streamorchestor-ms
- occhub-ingesthub-ms
- occhub-eventConsumer-service-ms

## uncategorized (full list)

_None_

## Skipped cells (sample)

- `tBObSOhZ74BR3jbHQjCu-1`: structural label — `ooo`
- `_J6kPRY2LQByNWtPyR75-10`: mainframe box (M1), not MS grid — `occhub-mf`
- `uiy4wioe-8W6FQFdPiAP-1`: structural label — `M1`
- `uiy4wioe-8W6FQFdPiAP-2`: structural label — `M2`
- `uiy4wioe-8W6FQFdPiAP-3`: structural label — `M3`
- `V0vlkF47L2H2bPEhkkEr-4`: structural label — `72`
- `V0vlkF47L2H2bPEhkkEr-1`: structural label — `M4`
- `V0vlkF47L2H2bPEhkkEr-2`: structural label — `M5`
- `V0vlkF47L2H2bPEhkkEr-3`: structural label — `M6`
- `uiy4wioe-8W6FQFdPiAP-6`: structural label — `M13`
- `V0vlkF47L2H2bPEhkkEr-5`: structural label — `M8`
- `V0vlkF47L2H2bPEhkkEr-6`: structural label — `M9`
- `uiy4wioe-8W6FQFdPiAP-7`: structural label — `M14`
- `V0vlkF47L2H2bPEhkkEr-7`: structural label — `M10`
- `V0vlkF47L2H2bPEhkkEr-8`: structural label — `M11`
- `V0vlkF47L2H2bPEhkkEr-9`: structural label — `M12`
- `uiy4wioe-8W6FQFdPiAP-11`: structural label — `SP`
- `uiy4wioe-8W6FQFdPiAP-12`: structural label — `External Services`
- `13qc9IiM3vek_g_TUGTT-1`: structural label — `M41`
- `13qc9IiM3vek_g_TUGTT-2`: structural label — `M42`
- `13qc9IiM3vek_g_TUGTT-3`: structural label — `M43`
- `13qc9IiM3vek_g_TUGTT-4`: structural label — `M44`
- `13qc9IiM3vek_g_TUGTT-5`: structural label — `M45`
- `13qc9IiM3vek_g_TUGTT-6`: structural label — `M46`
- `13qc9IiM3vek_g_TUGTT-7`: structural label — `M47`
- `13qc9IiM3vek_g_TUGTT-8`: structural label — `M48`
- `13qc9IiM3vek_g_TUGTT-9`: structural label — `M49`
- `13qc9IiM3vek_g_TUGTT-10`: structural label — `M50`
- `13qc9IiM3vek_g_TUGTT-11`: structural label — `M51`
- `VopO9QPev43YDlrnu2AW-18`: structural label — `Cron Job`
- `VopO9QPev43YDlrnu2AW-20`: structural label — `Shared Path`
- `VopO9QPev43YDlrnu2AW-31`: structural label — `Kafka Consumer`
- `VopO9QPev43YDlrnu2AW-32`: structural label — `Kafka Producer`
- `VopO9QPev43YDlrnu2AW-33`: structural label — `Joc kafka Topic's amq-streams-prod-kafka-bootstrap-amq-streams.apps.ocpappprdclu`
- `VopO9QPev43YDlrnu2AW-35`: structural label — `AIMS kafka Topic's amq-streams-prod-kafka-bootstrap-amq-streams.apps.ocpappprdcl`
- `VopO9QPev43YDlrnu2AW-39`: structural label — `occhub-streamorchestrator-ms-release Topic's`
- `i9CUAHzLTRYB6bYYJLQ8-4`: structural label — `M52`
- `i9CUAHzLTRYB6bYYJLQ8-5`: structural label — `M53`
- `i9CUAHzLTRYB6bYYJLQ8-6`: structural label — `M55`
- `i9CUAHzLTRYB6bYYJLQ8-7`: structural label — `M56`
- … and 55 more
