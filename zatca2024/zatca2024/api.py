import frappe
import os
import json
import base64
import re
import pyqrcode
from frappe.utils import now
from datetime import datetime
from zatca2024.zatca2024.createxml import (
    xml_tags, invoice_Typecode_Simplified, invoice_Typecode_Standard, 
    doc_Reference, additional_Reference, company_Data, customer_Data, 
    delivery_And_PaymentMeans, tax_Data, item_data, xml_structuring
)
from zatca2024.zatca2024.compliance import get_pwd, set_cert_path, create_compliance_x509, check_compliance

@frappe.whitelist(allow_guest=True)
def generate_signed_invoice_and_qr():
    try:
        obj1 = frappe.local.form_dict.get('obj1')  # Get 'obj1' from the request
        if not obj1:
            return {"error": "Missing 'obj1' in request data"}

        if isinstance(obj1, str):
            obj1 = json.loads(obj1)

        # Ensure 'is_return' is set to 0 if not present
        if 'is_return' not in obj1:
            obj1['is_return'] = 0

        # Prepare invoice data
        invoice = xml_tags()
        uuid1 = "some-unique-uuid"  # You can generate or receive this as needed

        if 'customer_data' in obj1:
            customer_doc = prepare_customer_doc(obj1['customer_data'])
        else:
            return {"error": "Missing 'customer_data' in request data"}

        if customer_doc.get("custom_b2c", 0) == 1:
            invoice = invoice_Typecode_Simplified(invoice, obj1)
        else:
            invoice = invoice_Typecode_Standard(invoice, obj1)

        invoice = doc_Reference(invoice, obj1, obj1.get("name"))
        invoice = additional_Reference(invoice)
        invoice = company_Data(invoice, obj1)
        invoice = customer_Data(invoice, obj1)
        invoice = delivery_And_PaymentMeans(invoice, obj1, obj1['is_return'])
        invoice = tax_Data(invoice, obj1)
        invoice = item_data(invoice, obj1)
        pretty_xml_string = xml_structuring(invoice, obj1)

        # Sign the invoice
        signed_xmlfile_name, path_string = sign_invoice(pretty_xml_string)
        qr_code_value = generate_qr_code(signed_xmlfile_name, path_string)
        hash_value = generate_hash(signed_xmlfile_name, path_string)

        response_data = {
            "signed_invoice": signed_xmlfile_name,
            "qr_code": qr_code_value
        }
        return response_data

    except Exception as e:
        return {"error": str(e)}

def prepare_customer_doc(customer_data):
    return {
        "customer_name": customer_data.get("customer_name"),
        "customer_group": customer_data.get("customer_group", "All Customer Groups"),
        "territory": customer_data.get("territory", "All Territories"),
        "custom_b2c": customer_data.get("custom_b2c", 0)
    }

def sign_invoice(xml_string):
    try:
        settings = frappe.get_doc('Zatca setting')
        xmlfile_name = 'finalzatcaxml.xml'
        signed_xmlfile_name = 'sdsign.xml'
        SDK_ROOT = settings.sdk_root
        path_string = f"export SDK_ROOT={SDK_ROOT} && export FATOORA_HOME=$SDK_ROOT/Apps && export SDK_CONFIG=config.json && export PATH=$PATH:$FATOORA_HOME &&  "
        
        with open(xmlfile_name, 'w') as f:
            f.write(xml_string)
        
        command_sign_invoice = path_string + f'fatoora -sign -invoice {xmlfile_name} -signedInvoice {signed_xmlfile_name}'
    except Exception as e:
        frappe.throw("While signing invoice an error occurred, inside sign_invoice: " + str(e))
    
    try:
        err, out = _execute_in_shell(command_sign_invoice)
        
        match = re.search(r'ERROR', err.decode("utf-8"))
        if match:
            frappe.throw(err)

        match = re.search(r'ERROR', out.decode("utf-8"))
        if match:
            frappe.throw(out)
        
        match = re.search(r'INVOICE HASH = (.+)', out.decode("utf-8"))
        if match:
            invoice_hash = match.group(1)
            return signed_xmlfile_name, path_string
        else:
            frappe.throw(err, out)
    except Exception as e:
        frappe.throw("An error occurred while signing invoice: " + str(e))

def generate_qr_code(signed_xmlfile_name, path_string):
    try:
        command_generate_qr = path_string + f'fatoora -qr -invoice {signed_xmlfile_name}'
        err, out = _execute_in_shell(command_generate_qr)
        qr_code_match = re.search(r'QR code = (.+)', out.decode("utf-8"))
        if qr_code_match:
            qr_code_value = qr_code_match.group(1)
            return qr_code_value
        else:
            frappe.msgprint("QR Code not found in the output.")
            return None
    except Exception as e:
        frappe.throw(f"Error in generating QR code: {e}")
        return None

def generate_hash(signed_xmlfile_name, path_string):
    try:
        command_generate_hash = path_string + f'fatoora -generateHash -invoice {signed_xmlfile_name}'
        err, out = _execute_in_shell(command_generate_hash)
        invoice_hash_match = re.search(r'INVOICE HASH = (.+)', out.decode("utf-8"))
        if invoice_hash_match:
            hash_value = invoice_hash_match.group(1)
            return hash_value
        else:
            frappe.msgprint("Hash value not found in the log entry.")
            return None
    except Exception as e:
        frappe.throw(f"Error in generating hash: {e}")
        return None

def _execute_in_shell(cmd, verbose=False, low_priority=False, check_exit_code=False):
    import shlex
    import tempfile
    from subprocess import Popen
    env_variables = {"MY_VARIABLE": "some_value", "ANOTHER_VARIABLE": "another_value"}
    if isinstance(cmd, list):
        cmd = shlex.join(cmd)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile as stderr:
        kwargs = {"shell": True, "stdout": stdout, "stderr": stderr}
        if low_priority:
            kwargs["preexec_fn"] = lambda: os.nice(10)
        p = Popen(cmd, **kwargs)
        exit_code = p.wait()
        stdout.seek(0)
        out = stdout.read()
        stderr.seek(0)
        err = stderr.read()
    failed = check_exit_code and exit_code

    if verbose or failed:
        if err:
            frappe.msgprint(err)
        if out:
            frappe.msgprint(out)
    if failed:
        raise Exception("Command failed")
    return err, out
