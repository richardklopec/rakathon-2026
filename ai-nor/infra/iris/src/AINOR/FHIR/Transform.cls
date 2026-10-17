/// The standard SDA3 -> FHIR R4 transformation of IRIS for Health, with the few changes AI NOR needs:
/// <ul>
/// <li>DocumentReference carries the inbox tag urn:ai-nor:inbox|nis (backend app/nis.py lists these),
/// the NIS patient id next to the Patient reference, a Czech document type and a sortable date;</li>
/// <li>a document sent again (same TXA-12) updates its DocumentReference instead of adding a second one;</li>
/// <li>Patient and Organization are created only once (conditional create).</li>
/// </ul>
/// Used as TransformClass of the production item "SDA3 na FHIR" (AINOR.Production).
Class AINOR.FHIR.Transform Extends HS.FHIR.DTL.Util.API.Transform.SDA3ToFHIR
{

/// Patient identifier system of the NIS (same as PATIENT_SYSTEM in backend app/nis.py)
Parameter PATIENTSYSTEM = "urn:fno:nis:patient";

/// Document number system (HL7 TXA-12)
Parameter DOCUMENTSYSTEM = "urn:fno:nis:document";

/// Inbox tag of AI NOR (INBOX_SYSTEM | INBOX_CODE in backend app/nis.py)
Parameter INBOXSYSTEM = "urn:ai-nor:inbox";

Parameter INBOXCODE = "nis";

/// Lookup table HL7 document type (table 0270, TXA-2) -> Czech name, editable in the Management Portal
Parameter DOCTYPETABLE = "AINOR.DocumentType";

Method TransformContainer(source As HS.SDA3.Container, patientId As %String = "") As HS.FHIR.DTL.Util.API.Transform.SDA3ToFHIR
{
	Set result = ##super(source, patientId)
	Do ..ForAiNor()
	Quit result
}

Method ForAiNor()
{
	// pass 1: the patient's NIS id (PID-3) gets the NIS system; Patient and Organization only once
	Set mrn = ""
	Set it = ..bundle.entry.%GetIterator()
	While it.%GetNext(, .entry) {
		Set r = entry.resource
		If r.resourceType = "Patient" {
			Set ids = r.identifier.%GetIterator()
			While ids.%GetNext(, .id) {
				If (mrn = "") || ($IsObject(id.type) && (id.type.text = "MRN")) {
					Set mrn = id.value, id.system = ..#PATIENTSYSTEM
				}
			}
			Set:mrn'="" entry.request.ifNoneExist = "identifier="_..#PATIENTSYSTEM_"|"_mrn
		} ElseIf (r.resourceType = "Organization") && $IsObject(r.identifier) && (r.identifier.%Size() > 0) {
			Set entry.request.ifNoneExist = "identifier="_r.identifier.%Get(0).value
		}
	}
	// pass 2: the documents, as the AI NOR inbox expects them
	Set it = ..bundle.entry.%GetIterator()
	While it.%GetNext(, .entry) {
		Set r = entry.resource
		Continue:r.resourceType'="DocumentReference"
		Set r.meta = {"tag": [{"system": (..#INBOXSYSTEM), "code": (..#INBOXCODE), "display": "AI NOR – ke zpracování"}]}
		Set:mrn'="" r.subject.identifier = {"system": (..#PATIENTSYSTEM), "value": (mrn)}
		Set code = "", number = ""
		If $IsObject(r.type) && $IsObject(r.type.coding) && (r.type.coding.%Size() > 0) {
			Set coding = r.type.coding.%Get(0), code = coding.code
			Set coding.system = "http://terminology.hl7.org/CodeSystem/v2-0270"
			Set r.type.text = ##class(Ens.Util.FunctionSet).Lookup(..#DOCTYPETABLE, code, code)
		}
		Set kind = $Select($IsObject(r.type)&&(r.type.text'=""):r.type.text,1:"Zpráva")
		Set r.description = kind_" z NIS (HL7v2 MDM, převod v IRIS)"
		Set att = r.content.%Get(0).attachment
		Set:att.contentType="text/plain" att.contentType = "text/plain; charset=utf-8"
		Set:att.title="" att.title = kind_$Select(att.contentType["text/plain":".txt",1:"")
		Set:att.creation'="" r.date = att.creation
		If $IsObject(att.extension) {
			Set ext = att.extension.%GetIterator()
			While ext.%GetNext(, .x) {
				Set:x.url["document-document-number" number = x.valueString
			}
		}
		If number '= "" {
			Set r.masterIdentifier = {"system": (..#DOCUMENTSYSTEM), "value": (number)}
			Set entry.request = {"method": "PUT", "url": ("DocumentReference?identifier="_..#DOCUMENTSYSTEM_"|"_number)}
		}
	}
}

}
