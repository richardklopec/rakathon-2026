# Mapování hlášení NOR → FHIR R4 (IRIS for Health)

Struktura podle **mCODE STU4**, pojmy podle **HL7 EU Common Cancer Model** (zatím jen logické modely), identifikátory a MKN-10 podle **HL7 CZ Core**.
Implementace: `backend/app/fhir/mapping.py` (co se zapíše) a `backend/app/fhir/sync.py` (kdy). Zapisují se pole s `review.state ∈ {auto_accepted, confirmed, edited}`, vše v jedné **transaction Bundle**. Každý zdroj nese `meta.tag` (`urn:ai-nor:review`: stav + jistota; `urn:ai-nor:report`: `preliminary` / `final`) a Provenance je zvlášť pro „přijato automaticky“ (agent AI) a „zkontrolováno člověkem“ (agent AI + verifier).

**Jeden záznam na případ, aktualizovaný na místě.** Kromě Patient (PUT podle identifieru) mají všechny zdroje stálé id z id případu
a zapisují se přes PUT (update-as-create), takže další zápis vytvoří novou verzi téhož zdroje (`_history`), ne druhý záznam:

| Zdroj | id | Po vytěžení (rozpracované) | Po potvrzení lékařem |
|---|---|---|---|
| `Composition` (hlášení jako celek, LOINC 72134-0 Cancer event report) | `{case}` | `status = preliminary`, sekce „Ke kontrole lékařem“ se seznamem polí, která ve FHIR ještě nejsou | `status = final`, `attester` (legal) = lékař, autor AI NOR + lékař |
| `Condition` | `{case}-dg` | `verificationStatus = provisional` | `confirmed` |
| `Observation` TNM / grading | `{case}-ct` … `{case}-pm`, `{case}-g` | `status = preliminary` | `status = final` |
| `DocumentReference` zdrojových zpráv | `{case}-d0` … | posílají se jen při prvním zápisu, novém vytěžení a změně pacienta | beze změny |
| `Provenance` | `{case}-prov-ai`, `{case}-prov-lekar` | `activity = CREATE`, pak `UPDATE` | + agent verifier |

Zdroj, který mezi zápisy vypadl (lékař pole zamítl), se v téže transakci smaže (`DELETE`). Do potvrzení tedy FHIR drží
neúplné hlášení: pole čekající na lékaře v něm nejsou, žádné není „potvrzené“ bez člověka.

**Příchozí zprávy z NIS (HL7v2 → FHIR v IRIS).** Produkce `AINOR.Production` (`infra/iris/src`, instaluje `scripts/setup_iris.py`):
`EnsLib.HL7.Service.TCPService` (MLLP, port 2575) → `AINOR.HL7.ToSDA3` (vestavěný `HS.Gateway.HL7.HL7ToSDA3`) →
`HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process` (vestavěný převod SDA3 → FHIR R4, `TransformClass` = `AINOR.FHIR.Transform`) →
`HS.FHIRServer.Interop.Operation` (FHIR server `/fhir/r4` uvnitř IRIS). `AINOR.FHIR.Transform` přidá k DocumentReference tag
`urn:ai-nor:inbox|nis`, identifikátor pacienta z PID-3 (`urn:fno:nis:patient`), typ dokumentu česky (TXA-2 přes tabulku
`AINOR.DocumentType`), `date` a `masterIdentifier` z TXA-12 (`urn:fno:nis:document`); stejná zpráva poslaná znovu
aktualizuje svůj DocumentReference (podmíněný PUT) a Patient / Organization se zakládají jen jednou (`ifNoneExist`).
Text zprávy: OBX typu TX (řádky) nebo ED (PDF v base64, `contentType` application/pdf).

| Pole NOR | FHIR | Kód / hodnota | Stav |
|---|---|---|---|
| Hlášení jako celek | `Composition` (preliminary → final, attester) | LOINC 72134-0 | ✅ |
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
