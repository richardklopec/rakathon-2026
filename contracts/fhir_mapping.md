# Mapování hlášení NOR → FHIR R4 (IRIS for Health)

Struktura podle **mCODE STU4**, pojmy podle **HL7 EU Common Cancer Model** (zatím jen logické modely), identifikátory a MKN-10 podle **HL7 CZ Core**.
Implementace: `backend/app/fhir/mapping.py`. Zapisují se jen pole s `review.state ∈ {confirmed, edited}`, vše v jedné **transaction Bundle**.

| Pole NOR | FHIR | Kód / hodnota | Stav |
|---|---|---|---|
| Pacient | `Patient` (PUT podle identifieru) | `urn:ai-nor:source-patient-id` (RČ: `https://ncez.mzcr.cz/fhir/sid/rcis`) | ✅ |
| Zdrojové zprávy | `DocumentReference` (text base64) | — | ✅ |
| Dg. MKN | `Condition` (mcode-primary-cancer-condition) `.code` | `https://uzis.cz/terminology/CodeSystem/mkn-10` | ✅ |
| Datum dg. | `Condition.onsetDateTime` | částečné datum (rok / rok-měsíc) | ✅ |
| Topografie + lateralita | `Condition.bodySite` + ext. `mcode-laterality-qualifier` | ICD-O-3; SNOMED 7771000 L / 24028007 P / 51440002 obě / 399488007 střed | ✅ |
| Morfologie | ext. `mcode-histology-morphology-behavior` | ICD-O-3 `8140/3` | ✅ |
| Grading | `Observation` mcode-histologic-grade | NCIt C18000 | ✅ |
| cT/cN/cM | `Observation` mcode-tnm-*-category | SNOMED 399504009 / 399534004 / 399387003 | ✅ |
| pT/pN/pM (y prefix) | totéž | SNOMED 384625004 / 371494008 / 371497001 | ✅ |
| Klinické stádium | `Observation` mcode-tnm-stage-group | 399537006 klin. / 399588009 pat.; method UICC NCIt C188404 | TODO |
| K dg. vedla vyšetření | `Condition.evidence` | | TODO |
| Metastázy (bitmask) | `Condition` mcode-secondary-cancer-condition (1 / orgán) | | TODO |
| Biomarkery | `Observation` mcode-tumor-marker-test | LOINC | TODO |
| Operace / RT / systémová léčba | `Procedure` (surgical, radiotherapy-course-summary 1217123003), `MedicationAdministration` | | TODO |
| Progrese / recidiva | `Observation` mcode-cancer-disease-status | LOINC 97509-4 | TODO |
| Původ údajů | `Provenance` (target = zapsané zdroje, entity = DocumentReference, agent = AI + ověřující lékař); `Observation.derivedFrom` → dokument | | ✅ |
