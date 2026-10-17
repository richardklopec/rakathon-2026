/// Reports from the hospital information system (NIS) into the AI NOR inbox, converted inside IRIS for Health:
/// HL7v2 MDM over MLLP (port 2575) -> SDA3 (built-in HS.Gateway.HL7.HL7ToSDA3) -> FHIR R4 (built-in SDA3 -> FHIR
/// process with AINOR.FHIR.Transform) -> IRIS FHIR server /fhir/r4 as DocumentReference tagged urn:ai-nor:inbox|nis.
/// Installed and started by backend/scripts/setup_iris.py; messages can be traced in the Management Portal
/// (Interoperability > Messages). Demo sender: backend/scripts/nis_demo_send.py.
Class AINOR.Production Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="AINOR.Production" TestingEnabled="false" LogGeneralTraceEvents="false">
  <Description>Zprávy z NIS (HL7v2 MDM) do schránky AI NOR v IRIS FHIR</Description>
  <ActorPoolSize>1</ActorPoolSize>
  <Item Name="NIS HL7v2 MLLP" Category="AI NOR" ClassName="EnsLib.HL7.Service.TCPService" PoolSize="1" Enabled="true" Comment="Zprávy z nemocničního systému (MLLP, port 2575)">
    <Setting Target="Adapter" Name="Port">2575</Setting>
    <Setting Target="Adapter" Name="StayConnected">300</Setting>
    <Setting Target="Host" Name="MessageSchemaCategory">2.5</Setting>
    <Setting Target="Host" Name="TargetConfigNames">HL7 na SDA3</Setting>
    <Setting Target="Host" Name="DefCharEncoding">UTF-8</Setting>
  </Item>
  <Item Name="HL7 na SDA3" Category="AI NOR" ClassName="AINOR.HL7.ToSDA3" PoolSize="1" Enabled="true" Comment="Vestavěný převod HL7v2 na SDA3">
    <Setting Target="Host" Name="TargetConfigName">SDA3 na FHIR</Setting>
  </Item>
  <Item Name="SDA3 na FHIR" Category="AI NOR" ClassName="HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process" PoolSize="1" Enabled="true" Comment="Vestavěný převod SDA3 na FHIR R4, úpravy pro AI NOR v AINOR.FHIR.Transform">
    <Setting Target="Host" Name="TargetConfigName">IRIS FHIR server</Setting>
    <Setting Target="Host" Name="TransformClass">AINOR.FHIR.Transform</Setting>
    <Setting Target="Host" Name="FHIRMetadataSet">HL7v40</Setting>
    <Setting Target="Host" Name="FHIREndpoint">/fhir/r4</Setting>
  </Item>
  <Item Name="IRIS FHIR server" Category="AI NOR" ClassName="HS.FHIRServer.Interop.Operation" PoolSize="1" Enabled="true" Comment="Zápis transakce do FHIR serveru /fhir/r4 (uvnitř IRIS, bez HTTP)">
  </Item>
</Production>
}

}
