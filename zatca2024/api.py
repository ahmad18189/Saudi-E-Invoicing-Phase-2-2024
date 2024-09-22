import frappe
import requests
import json
import re
import base64
import xml.etree.ElementTree as ET
from xml.dom import minidom
from zatca2024.createxml import (
    xml_tags, salesinvoice_data, invoice_Typecode_Simplified, invoice_Typecode_Standard, 
    doc_Reference, additional_Reference, company_Data, customer_Data, 
    delivery_And_PaymentMeans, tax_Data, item_data, xml_structuring, 
    invoice_Typecode_Compliance, delivery_And_PaymentMeans_for_Compliance, 
    doc_Reference_compliance, get_tax_total_from_items
)

@frappe.whitelist(allow_guest=True)
def api_sign_invoice():
    try:
        data = frappe.local.form_dict
        invoice_data = data.get("invoice_data")
        
        signed_invoice, uuid1, signed_xmlfile_name, qr_code_value, hash_value, custom_uuid, custom_zatca_status, xml_cleared = sign_invoice_logic(invoice_data)

        if isinstance(signed_invoice, ET.Element):
            signed_invoice_str = ET.tostring(signed_invoice, encoding='utf-8')
            signed_invoice_str = signed_invoice_str.decode('utf-8')
            pretty_xml = minidom.parseString(signed_invoice_str).toprettyxml(indent="  ")
            return json.dumps({"signed_invoice": signed_invoice_str, "uuid": uuid1, "signed_xmlfile_name": signed_xmlfile_name, "qr_code_value": qr_code_value, "hash_value": hash_value, "custom_uuid": custom_uuid, "custom_zatca_status": custom_zatca_status, "xml_cleared": xml_cleared})
        else:
            return json.dumps({"signed_invoice": signed_invoice, "uuid": uuid1, "signed_xmlfile_name": signed_xmlfile_name, "qr_code_value": qr_code_value, "hash_value": hash_value, "custom_uuid": custom_uuid, "custom_zatca_status": custom_zatca_status, "xml_cleared": xml_cleared})
    
    except Exception as e:
        frappe.throw("Error in signing invoice: " + str(e))

def sign_invoice_logic(invoice_data):
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    signed_invoice = invoice_data
    signed_invoice['signed'] = True

    try:
        settings = frappe.get_doc('Zatca setting')
        
        if settings.zatca_invoice_enabled != 1:
            frappe.throw("Zatca Invoice is not enabled in Zatca Settings, Please contact your system administrator")
        
        invoice_number = invoice_data.get("name")
        
        sales_invoice_doc = invoice_data

        if sales_invoice_doc['custom_zatca_status'] in ["REPORTED", "CLEARED"]:
            frappe.throw("Already submitted to Zakat and Tax Authority")
        signed_invoice, uuid1, signed_xmlfile_name, qr_code_value, hash_value, custom_uuid, custom_zatca_status, xml_cleared = zatca_Call(sales_invoice_doc, 0)

        return signed_invoice, uuid1, signed_xmlfile_name, qr_code_value, hash_value, custom_uuid, custom_zatca_status, xml_cleared
        
    except Exception as e:
        frappe.throw("Error in background call: " + str(e))

def zatca_Call(sales_invoice_doc, compliance_type="0"):
    compliance_type = "0"
    invoice = xml_tags()
    invoice, uuid1, sales_invoice_doc = salesinvoice_data(invoice, sales_invoice_doc)
    
    custom_b2c = sales_invoice_doc["custom_b2c"]
    
    if compliance_type == "0":
        if custom_b2c == 1:
            invoice = invoice_Typecode_Simplified(invoice, sales_invoice_doc)
        else:
            invoice = invoice_Typecode_Standard(invoice, sales_invoice_doc)
    else:
        invoice = invoice_Typecode_Compliance(invoice, compliance_type)
    
    invoice = doc_Reference(invoice, sales_invoice_doc, sales_invoice_doc["name"])
    invoice = additional_Reference(invoice)
    invoice = company_Data(invoice, sales_invoice_doc)
    invoice = customer_Data(invoice, sales_invoice_doc)
    invoice = delivery_And_PaymentMeans(invoice, sales_invoice_doc, sales_invoice_doc["is_return"])
    invoice = tax_Data(invoice, sales_invoice_doc)
    invoice = item_data(invoice, sales_invoice_doc)
    print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print(invoice)
    print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print(sales_invoice_doc)
    print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    pretty_xml_string = xml_structuring(invoice, sales_invoice_doc)
    signed_xmlfile_name, path_string = sign_invoice()
    qr_code_value = generate_qr_code(signed_xmlfile_name, sales_invoice_doc, path_string)
    hash_value = generate_hash(signed_xmlfile_name, path_string)
    xml_cleared = None
    if compliance_type == "0":
        if sales_invoice_doc["custom_b2c"] == 1:
            custom_uuid, custom_zatca_status = reporting_API(uuid1, hash_value, signed_xmlfile_name, sales_invoice_doc["name"])
        else:
            xml_cleared, custom_uuid, custom_zatca_status = clearance_API(uuid1, hash_value, signed_xmlfile_name, sales_invoice_doc["name"], sales_invoice_doc)

    return pretty_xml_string, uuid1, signed_xmlfile_name, qr_code_value, hash_value, custom_uuid, custom_zatca_status, xml_cleared

def _execute_in_shell(cmd, verbose=False, low_priority=False, check_exit_code=False):
    import shlex
    import tempfile
    from subprocess import Popen
    env_variables = {"MY_VARIABLE": "some_value", "ANOTHER_VARIABLE": "another_value"}
    if isinstance(cmd, list):
        cmd = shlex.join(cmd)

    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        kwargs = {"shell": True, "stdout": stdout, "stderr": stderr}
        if low_priority:
            kwargs["preexec_fn"] = lambda: os.nice(10)
        p = Popen(cmd, **kwargs)
        exit_code = p.wait()
        stdout.seek(0)
        out = stdout.read()
        stderr.seek(0)
        err = stderr.read()
    
    if check_exit_code and exit_code:
        raise Exception("Command failed")

    if verbose:
        if err:
            frappe.msgprint(err)
        if out:
            frappe.msgprint(out)

    return err, out

def sign_invoice():
    try:
        settings = frappe.get_doc('Zatca setting')
        xmlfile_name = 'finalzatcaxml.xml'
        signed_xmlfile_name = 'sdsign.xml'
        SDK_ROOT = settings.sdk_root
        path_string = f"export SDK_ROOT={SDK_ROOT} && export FATOORA_HOME=$SDK_ROOT/Apps && export SDK_CONFIG=config.json && export PATH=$PATH:$FATOORA_HOME &&"
        
        command_sign_invoice = path_string + f' fatoora -sign -invoice {xmlfile_name} -signedInvoice {signed_xmlfile_name}'
    except Exception as e:
        frappe.throw("While signing invoice, an error occurred inside sign_invoice: " + str(e))
    
    try:
        err, out = _execute_in_shell(command_sign_invoice)
        
        if re.search(r'ERROR', err.decode("utf-8")):
            frappe.throw(err)
        if re.search(r'ERROR', out.decode("utf-8")):
            frappe.throw(out)
        
        match = re.search(r'INVOICE HASH = (.+)', out.decode("utf-8"))
        if match:
            invoice_hash = match.group(1)
            return signed_xmlfile_name, path_string
        else:
            frappe.throw(err, out)
    except Exception as e:
        frappe.throw("An error occurred signing invoice: " + str(e))

def generate_qr_code(signed_xmlfile_name, sales_invoice_doc, path_string):
    try:
        with open(signed_xmlfile_name, 'r') as file:
            file_content = file.read()
        command_generate_qr = path_string + f' fatoora -qr -invoice {signed_xmlfile_name}'
        err, out = _execute_in_shell(command_generate_qr)
        qr_code_match = re.search(r'QR code = (.+)', out.decode("utf-8"))
        if qr_code_match:
            qr_code_value = qr_code_match.group(1)
            return qr_code_value
        else:
            frappe.msgprint("QR Code not found in the output.")
    except Exception as e:
        frappe.throw(f"Error in generating QR code: {e}")

def generate_hash(signed_xmlfile_name, path_string):
    try:
        command_generate_hash = path_string + f' fatoora -generateHash -invoice {signed_xmlfile_name}'
        err, out = _execute_in_shell(command_generate_hash)
        invoice_hash_match = re.search(r'INVOICE HASH = (.+)', out.decode("utf-8"))
        if invoice_hash_match:
            hash_value = invoice_hash_match.group(1)
            return hash_value
        else:
            frappe.msgprint("Hash value not found in the log entry.")
    except Exception as e:
        frappe.throw(f"Error in generating hash: {e}")

def validate_invoice(signed_xmlfile_name, path_string):
    try:
        command_validate_hash = path_string + f' fatoora -validate -invoice {signed_xmlfile_name}'
        err, out = _execute_in_shell(command_validate_hash)
        pattern_global_result = re.search(r'\*\*\* GLOBAL VALIDATION RESULT = (\w+)', out.decode("utf-8"))
        global_result = pattern_global_result.group(1) if pattern_global_result else None
        global_validation_result = 'PASSED' if global_result == 'PASSED' else 'FAILED'
        if global_validation_result == 'FAILED':
            frappe.msgprint(out)
            frappe.msgprint(err)
            frappe.throw("Validation failed")
        else:
            frappe.msgprint("Validation done successfully")
    except Exception as e:
        frappe.throw(f"An error occurred validating invoice: {str(e)}")

def xml_base64_Decode(signed_xmlfile_name):
    try:
        with open(signed_xmlfile_name, "r") as file:
            xml = file.read().lstrip()
            base64_encoded = base64.b64encode(xml.encode("utf-8"))
            base64_decoded = base64_encoded.decode("utf-8")
            return base64_decoded
    except Exception as e:
        frappe.throw("Error in XML base64 decoding: " + str(e))

def reporting_API(uuid1, hash_value, signed_xmlfile_name, invoice_number):
    try:
        custom_uuid = None 
        custom_zatca_status = None
        settings = frappe.get_doc('Zatca setting')
        payload = json.dumps({
            "invoiceHash": hash_value,
            "uuid": uuid1,
            "invoice": xml_base64_Decode(signed_xmlfile_name),
        })
        headers = {
            'accept': 'application/json',
            'accept-language': 'en',
            'Clearance-Status': '0',
            'Accept-Version': 'V2',
            'Authorization': 'Basic ' + settings.basic_auth_production,
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url=get_API_url("invoices/reporting/single"), headers=headers, data=payload)
        
        if response.status_code in (400, 405, 406, 409):
            custom_uuid = 'Not Submitted'
            custom_zatca_status = 'Not Submitted'
            frappe.throw("Error: The request you are sending to Zatca is in incorrect format. Status code: " + str(response.status_code) + "<br><br> " + response.text)
        
        if response.status_code in (401, 403, 407, 451):
            custom_uuid = 'Not Submitted'
            custom_zatca_status = 'Not Submitted'
            frappe.throw("Error: Zatca Authentication failed. Status code: " + str(response.status_code) + "<br><br> " + response.text)
        
        if response.status_code not in (200, 202):
            custom_uuid = 'Not Submitted'
            custom_zatca_status = 'Not Submitted'
            frappe.throw("Error: Zatca server busy or not responding. Status code: " + str(response.status_code) + "<br><br> " + response.text)
        
        if response.status_code in (200, 202):
            if response.status_code == 202:
                msg = "REPORTED WITH WARNINGS: <br><br> Please copy the below message and send it to your system administrator to fix these warnings before next submission <br><br><br> "
            if response.status_code == 200:
                msg = "SUCCESS: <br><br> "
            
            msg = msg + "Status Code: " + str(response.status_code) + "<br><br> "
            msg = msg + "Zatca Response: " + response.text + "<br><br> "
            frappe.msgprint(msg)
            settings.pih = hash_value
            settings.save(ignore_permissions=True)
            
            custom_uuid = uuid1 
            custom_zatca_status = 'REPORTED'
            success_Log(response.text, uuid1, invoice_number)
            return custom_uuid, custom_zatca_status
        else:
            error_Log()
    except Exception as e:
        frappe.throw("Error in reporting API: " + str(e))

def success_Log(response, uuid1, invoice_number):
    try:
        current_time = frappe.utils.now()
        frappe.get_doc({
            "doctype": "Zatca Success log",
            "title": "Zatca invoice call done successfully",
            "message": "This message by Zatca Compliance",
            "uuid": uuid1,
            "invoice_number": invoice_number,
            "time": current_time,
            "zatca_response": response  
        }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.throw("Error in success log: " + str(e))

def error_Log():
    try:
        frappe.log_error(title='Zatca invoice call failed in clearance status', message=frappe.get_traceback())
    except Exception as e:
        frappe.throw("Error in error log: " + str(e))

def get_API_url(base_url):
    try:
        settings = frappe.get_doc('Zatca setting')
        if settings.select == "Sandbox":
            url = settings.sandbox_url + base_url
        elif settings.select == "Simulation":
            url = settings.simulation_url + base_url
        else:
            url = settings.production_url + base_url
        return url 
    except Exception as e:
        frappe.throw("Error getting URL: " + str(e))

def clearance_API(uuid1, hash_value, signed_xmlfile_name, invoice_number, sales_invoice_doc):
    try:
        settings = frappe.get_doc('Zatca setting')
        payload = json.dumps({
            "invoiceHash": hash_value,
            "uuid": uuid1,
            "invoice": xml_base64_Decode(signed_xmlfile_name),
        })
        headers = {
            'accept': 'application/json',
            'accept-language': 'en',
            'Clearance-Status': '1',
            'Accept-Version': 'V2',
            'Authorization': 'Basic ' + settings.basic_auth_production,
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url=get_API_url("invoices/clearance/single"), headers=headers, data=payload)
        
        if response.status_code in (400, 405, 406, 409):
            custom_uuid = 'Not Submitted'
            custom_zatca_status = 'Not Submitted'
            frappe.throw("Error: The request you are sending to Zatca is in incorrect format. Status code: " + str(response.status_code) + "<br><br> " + response.text)
        
        if response.status_code in (401, 403, 407, 451):
            custom_uuid = 'Not Submitted'
            custom_zatca_status = 'Not Submitted'
            frappe.throw("Error: Zatca Authentication failed. Status code: " + str(response.status_code) + "<br><br> " + response.text)
        
        if response.status_code not in (200, 202):
            custom_uuid = 'Not Submitted'
            custom_zatca_status = 'Not Submitted'
            frappe.throw("Error: Zatca server busy or not responding. Status code: " + str(response.status_code))
        
        if response.status_code in (200, 202):
            if response.status_code == 202:
                msg = "CLEARED WITH WARNINGS: <br><br> Please copy the below message and send it to your system administrator to fix these warnings before next submission <br><br><br> "
            if response.status_code == 200:
                msg = "SUCCESS: <br><br> "
            
            msg = msg + "Status Code: " + str(response.status_code) + "<br><br> "
            msg = msg + "Zatca Response: " + response.text + "<br><br> "
            frappe.msgprint(msg)
            settings.pih = hash_value
            settings.save(ignore_permissions=True)
            
            custom_uuid = uuid1 
            custom_zatca_status = 'CLEARED'
            
            data = json.loads(response.text)
            base64_xml = data["clearedInvoice"] 
            xml_cleared = base64.b64decode(base64_xml).decode('utf-8')
            success_Log(response.text, uuid1, invoice_number)
            return xml_cleared, custom_uuid, custom_zatca_status
        else:
            error_Log()
    except Exception as e:
        frappe.throw("Error in clearance API: " + str(e))
