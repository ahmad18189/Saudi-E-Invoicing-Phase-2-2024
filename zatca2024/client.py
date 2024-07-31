import frappe
import requests
import json
import base64
import os
import codecs
import pyqrcode

def on_submit_sales_invoice(doc, method):
    try:
        url = 'http://104.248.232.238/api/method/zatca2024.api.api_sign_invoice'
        headers = {
            'Authorization': 'Token cc90000abd8fdbb:c6c8e2b60e28e62',
            'Content-Type': 'application/json'
        }
        
        invoice_data = json.loads(frappe.as_json(doc))
        payload = {'invoice_data': invoice_data}

        print("Payload being sent to API:")
        print(json.dumps(payload, indent=4))

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        print("Response from API:")
        print(response.text)

        if response.status_code == 200:
            result = json.loads(response.json().get('message'))
            signed_invoice = result.get('signed_invoice')
            qr_code_value = result.get('qr_code_value')
            xml_cleared= result.get('xml_cleared')
            uuid_value = result.get('uuid')
            signed_xmlfile_name = "{}_{}".format(doc.name, result.get('signed_xmlfile_name'))
            
            print("Parsed result from API response:")
            print("Signed Invoice:", signed_invoice)
            print("QR Code Value:", qr_code_value)
            print("UUID Code Value:", uuid_value)
            print("Signed XML File Name:", signed_xmlfile_name)
            if uuid_value :
                doc.db_set('custom_uuid' , uuid_value, commit=True  , update_modified=True)
            # Save the signed invoice manually
            if signed_invoice:
                try:
                    site_path = frappe.get_site_path()
                    signed_invoice_path = os.path.join(site_path, 'public', 'files', signed_xmlfile_name)
                    with codecs.open(signed_invoice_path, 'w', 'utf-8') as f:
                        f.write(signed_invoice)
                    print("Signed invoice saved successfully at:", signed_invoice_path)
                    
                    # Attach the file to the Sales Invoice in Frappe
                    signed_invoice_attachment = frappe.get_doc({
                        "doctype": "File",
                        "file_name": signed_xmlfile_name,
                        "attached_to_doctype": "Sales Invoice",
                        "attached_to_name": doc.name,
                        "file_url": '/files/' + signed_xmlfile_name
                    })
                    signed_invoice_attachment.save(ignore_permissions=True)
                except Exception as e:
                    print("Error saving signed invoice:")
                    print(str(e))
                    frappe.throw("Error saving signed invoice: {0}".format(str(e)))
            
            # Save the signed invoice manually
            if xml_cleared and doc.custom_b2c == 0 :
                try:
                    site_path = frappe.get_site_path()
                    signed_invoice_path = os.path.join(site_path, 'public', 'files', "cleared-"+signed_xmlfile_name)
                    with codecs.open(signed_invoice_path, 'w', 'utf-8') as f:
                        f.write(xml_cleared)
                    print("Signed invoice saved successfully at:", signed_invoice_path)
                    
                    # Attach the file to the Sales Invoice in Frappe
                    signed_invoice_attachment = frappe.get_doc({
                        "doctype": "File",
                        "file_name": "cleared-"+signed_xmlfile_name,
                        "attached_to_doctype": "Sales Invoice",
                        "attached_to_name": doc.name,
                        "file_url": '/files/' + "cleared-"+signed_xmlfile_name
                    })
                    signed_invoice_attachment.save(ignore_permissions=True)
                except Exception as e:
                    print("Error saving signed invoice:")
                    print(str(e))
                    frappe.throw("Error saving signed invoice: {0}".format(str(e)))
                
            # Save the QR code manually
            if qr_code_value:
                try:
                    print("QR code value:", qr_code_value)
                    qr = pyqrcode.create(qr_code_value)
                    qr_code_file_name = "{}_qr_code.png".format(doc.name)
                    qr_code_path = os.path.join(site_path, 'public', 'files', qr_code_file_name)
                    print(qr_code_path)
                    qr.png(qr_code_path, scale=5)
                    print("QR code saved successfully at:", qr_code_path)
                    
                    # Attach the file to the Sales Invoice in Frappe
                    qr_code_attachment = frappe.get_doc({
                        "doctype": "File",
                        "file_name": qr_code_file_name,
                        "attached_to_doctype": "Sales Invoice",
                        "attached_to_name": doc.name,
                        "file_url": '/files/' + qr_code_file_name
                    })
                    qr_code_attachment.save(ignore_permissions=True)
                    print("QR code attached successfully.")
                except Exception as e:
                    print("Error decoding or saving QR code:")
                    print(str(e))
                    frappe.throw("Error decoding or saving QR code: {0}".format(str(e)))
        else:
            frappe.throw("Failed to sign invoice: {0}".format(response.text))
    
    except Exception as e:
        print("Error in on_submit_sales_invoice:")
        print(str(e))
        frappe.throw("Error in on_submit_sales_invoice: {0}".format(str(e)))

# Register the hook to be called on submit of Sales Invoice
doc_events = {
    "Sales Invoice": {
        "on_submit": on_submit_sales_invoice
    }
}
