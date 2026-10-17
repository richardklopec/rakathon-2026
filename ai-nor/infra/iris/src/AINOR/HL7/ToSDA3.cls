/// HL7v2 document message from the hospital information system (MDM^T02 and other MDM events) to SDA3,
/// with the converter built into IRIS for Health (HS.Gateway.HL7.HL7ToSDA3). The SDA3 then goes to the
/// built-in SDA3 -> FHIR process (HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process with AINOR.FHIR.Transform).
/// Messages that carry no document (ADT, ORM, ...) are acknowledged and left out: AI NOR reads reports only.
Class AINOR.HL7.ToSDA3 Extends Ens.BusinessProcess [ ClassType = persistent ]
{

/// Where the SDA3 goes (production item of class HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process)
Property TargetConfigName As Ens.DataType.ConfigName [ InitialExpression = "SDA3 na FHIR" ];

Parameter SETTINGS = "TargetConfigName:Basic:selector?context={Ens.ContextSearch/ProductionItems?targets=1&productionName=@productionId}";

Method OnRequest(pRequest As EnsLib.HL7.Message, Output pResponse As Ens.Response) As %Status
{
	Set type = pRequest.GetValueAt("MSH:9.1")
	If type '= "MDM" {
		$$$LOGINFO("Zpráva "_type_"^"_pRequest.GetValueAt("MSH:9.2")_" nenese dokument, AI NOR ji nepotřebuje")
		Quit $$$OK
	}
	Set sc = ##class(HS.Gateway.HL7.HL7ToSDA3).GetSDA(pRequest, .sda)
	Quit:$$$ISERR(sc) sc
	Set msg = ##class(HS.Message.XMLMessage).%New()
	Set msg.Name = "AINOR "_type_"^"_pRequest.GetValueAt("MSH:9.2")
	Do msg.ContentStream.CopyFrom(sda)
	Quit ..SendRequestSync(..TargetConfigName, msg, .pResponse)
}

}
