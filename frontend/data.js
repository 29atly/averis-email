(function () {
  const fieldDefinitions = [
    ['shipper', 'Shipper'], ['consignee', 'Consignee'], ['notify_party', 'Notify party'],
    ['port_of_loading', 'Port of loading'], ['port_of_discharge', 'Port of discharge'],
    ['container_count', 'Container count'], ['gross_weight_kg', 'Gross weight']
  ];
  const evidence = (file, page, text, raw, normalized) => ({ file_path: file, page_number: page, source_text: text, raw, normalized });
  const cases = [
    {
      id: 'email_517', subject: 'RE_ TO CONFIRM DOCS _ 5RCY-95001 _ CALLAO_PERU _ BALL & DOGGETT AUSTRALIA PTY LTD _ MEDUUD661016',
      sender: 'deswita_elvyani@aprilasia.com', recipient: 'Operations Team', time: '10:42', receivedLabel: 'Today at 10:42',
      category: 'bl_comparison', status: 'review',
      body: 'Dear Team,\n\nPlease compare the SI and draft BL for MSDUL0942583113. Some SI fields were left blank by the customer; kindly confirm what we have.',
      reviewFields: ['port_of_loading', 'port_of_discharge'], reviewReasonCode: 'missing_value',
      reviewReason: 'The Shipping Instruction contains missing or placeholder port values. Confirm the intended values before completing the comparison.',
      siFile: 'email_517_SI.txt', blFile: 'email_517_BL.txt', processingTime: '1.8s',
      values: {
        shipper: [evidence('email_517_SI.txt',1,'Shipper/Exporter: APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD'), evidence('email_517_BL.txt',1,'SHIPPER: APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD')],
        consignee: [evidence('email_517_SI.txt',1,'To the Order of: BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD'), evidence('email_517_BL.txt',1,'Consignee (Non-Negotiable): BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD')],
        notify_party: [evidence('email_517_SI.txt',1,'NOTIFY PARTY: BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD'), evidence('email_517_BL.txt',1,'Notify: BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD','BALL & DOGGETT AUSTRALIA PTY LTD')],
        port_of_loading: [evidence('email_517_SI.txt',1,'Port of Loading (POL): ____MT','____MT',null), evidence('email_517_BL.txt',1,'Load Port: SINGAPORE (SGSIN)','SINGAPORE (SGSIN)','SINGAPORE')],
        port_of_discharge: [evidence('email_517_SI.txt',1,'Port of Discharge (POD): TBA','TBA',null), evidence('email_517_BL.txt',1,'Port of Discharge: CALLAO, PERU (PECLL)','CALLAO, PERU (PECLL)','CALLAO, PERU')],
        container_count: [evidence('email_517_SI.txt',1,"Total Containers: 15 x 20'GP","15 x 20'GP",15), evidence('email_517_BL.txt',1,"No. of Containers or Packages: 15 x 20'GP","15 x 20'GP",15)],
        gross_weight_kg: [evidence('email_517_SI.txt',1,'GROSS WEIGHT: 340,770 KG','340,770 KG',340770), evidence('email_517_BL.txt',1,'Gross Weight (KG): 340,770 KG','340,770 KG',340770)]
      }
    },
    {
      id: 'email_004', subject: 'REQUEST BL DRAFT _ PO 26067_ COATED IVORY BOARD__138MT', sender: 'docs@vitalsolutions.sg', recipient: 'Mitchelle',
      time: '09:18', receivedLabel: 'Today at 09:18', category: 'bl_comparison', status: 'complete',
      body: `Hi Mitchelle,

Attached are the SI and draft BL for OC 5ALT-01226 (COATED IVORY BOARD). Please check the details and confirm.

Best Regards,
Deswita Elvyani
Shipping Documentation
DID : +971 04 4938298
APRIL Fine Paper Trading (Middle East) Fze
#813, 4 EA, Dubai Airport Free Zone
P.O. Box : 293775, Dubai, United Arab Emirates
Website : www.aprilasia.com | www.paperone.com`,
      siFile: 'email_004_SI.txt', blFile: 'email_004_BL.txt', processingTime: '1.6s',
      values: {
        shipper: [evidence('email_004_SI.txt',1,'Shipper: APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD'), evidence('email_004_BL.txt',1,'SHIPPER: APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD')],
        consignee: [evidence('email_004_SI.txt',1,'Consignee (Non-Negotiable): EAST BRIGHT FZ-LLC','EAST BRIGHT FZ-LLC','EAST BRIGHT FZ-LLC'), evidence('email_004_BL.txt',1,'To the Order of: UAB NOVAKOPA','UAB NOVAKOPA','UAB NOVAKOPA')],
        notify_party: [evidence('email_004_SI.txt',1,'Notify: EAST BRIGHT FZ-LLC','EAST BRIGHT FZ-LLC','EAST BRIGHT FZ-LLC'), evidence('email_004_BL.txt',1,'Notify Party: UAB NOVAKOPA','UAB NOVAKOPA','UAB NOVAKOPA')],
        port_of_loading: [evidence('email_004_SI.txt',1,'Port of Loading (POL): NANTONG, CHINA (CNNTG)','NANTONG, CHINA (CNNTG)','NANTONG, CHINA'), evidence('email_004_BL.txt',1,'Port of Loading (POL): NANTONG, CHINA (CNNTG)','NANTONG, CHINA (CNNTG)','NANTONG, CHINA')],
        port_of_discharge: [evidence('email_004_SI.txt',1,'POD: KARACHI, PAKISTAN (PKKHI)','KARACHI, PAKISTAN (PKKHI)','KARACHI, PAKISTAN'), evidence('email_004_BL.txt',1,'POD: KARACHI, PAKISTAN (PKKHI)','KARACHI, PAKISTAN (PKKHI)','KARACHI, PAKISTAN')],
        container_count: [evidence('email_004_SI.txt',1,"Total Containers: 6 x 40'HC","6 x 40'HC",6), evidence('email_004_BL.txt',1,"Container Count: 6 x 40'HC","6 x 40'HC",6)],
        gross_weight_kg: [evidence('email_004_SI.txt',1,'Gross Wt (kgs): 131,058 KG','131,058 KG',131058), evidence('email_004_BL.txt',1,'Gross Weight (KG): 131,058 KG','131,058 KG',131058)]
      }
    },
    {
      id: 'email_001', subject: 'TO CONFIRM DOCS _ 5RSG-00133 _ CALLAO_PERU _ MOORIM SP CO., LTD _ MEDUUD104332', sender: 'aziztz@safqa.co.ke', recipient: 'Najiha',
      time: 'Yesterday', receivedLabel: 'Yesterday at 16:27', category: 'bl_comparison', status: 'complete',
      body: `Hi Najiha,

Attached are the SI and draft BL for OC 5RSG-00133 (PAPERONE DIGITAL COPIER PAPER). Please check the details and confirm.

Best Regards,
Willy Situmorang
Shipping Documentation
DID : +971 04 4938289
APRIL Fine Paper Trading (Middle East) Fze
#813, 4 EA, Dubai Airport Free Zone
P.O. Box : 293775, Dubai, United Arab Emirates
Website : www.aprilasia.com | www.paperone.com`,
      siFile: 'email_001_SI.txt', blFile: 'email_001_BL.txt', processingTime: '1.4s',
      values: {
        shipper: [evidence('email_001_SI.txt',1,'Shipper/Exporter: APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD'), evidence('email_001_BL.txt',1,'SHIPPER: APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD','APRIL FAR EAST (M) SDN BHD')],
        consignee: [evidence('email_001_SI.txt',1,'CONSIGNEE: MOORIM SP CO., LTD','MOORIM SP CO., LTD','MOORIM SP CO., LTD'), evidence('email_001_BL.txt',1,'CONSIGNEE: MOORIM SP CO., LTD','MOORIM SP CO., LTD','MOORIM SP CO., LTD')],
        notify_party: [evidence('email_001_SI.txt',1,'NOTIFY PARTY: UAB NOVAKOPA','UAB NOVAKOPA','UAB NOVAKOPA'), evidence('email_001_BL.txt',1,'Notify: UAB NOVAKOPA','UAB NOVAKOPA','UAB NOVAKOPA')],
        port_of_loading: [evidence('email_001_SI.txt',1,'Port of Loading: PORT KLANG (WESTPORT), MALAYSIA (MYPKG)','PORT KLANG (WESTPORT), MALAYSIA (MYPKG)','PORT KLANG, MALAYSIA'), evidence('email_001_BL.txt',1,'Port of Loading (POL): PORT KLANG (WESTPORT), MALAYSIA (MYPKG)','PORT KLANG (WESTPORT), MALAYSIA (MYPKG)','PORT KLANG, MALAYSIA')],
        port_of_discharge: [evidence('email_001_SI.txt',1,'Discharge Port: CALLAO, PERU (PECLL)','CALLAO, PERU (PECLL)','CALLAO, PERU'), evidence('email_001_BL.txt',1,'POD: CALLAO, PERU (PECLL)','CALLAO, PERU (PECLL)','CALLAO, PERU')],
        container_count: [evidence('email_001_SI.txt',1,"No. of Containers or Packages: 1 x 40'HC","1 x 40'HC",1), evidence('email_001_BL.txt',1,"Container Count: 1 x 40'HC","1 x 40'HC",1)],
        gross_weight_kg: [evidence('email_001_SI.txt',1,'Gross Weight (KG): 21,577 KG','21,577 KG',21577), evidence('email_001_BL.txt',1,'Gross Wt (kgs): 21,577 KG','21,577 KG',21577)]
      }
    },
    { id: 'email_110', subject: 'RE_ CUST SI _ MEA _ 5RCY-51168 __ PO_25_3508', sender: 'sokyong_ooi@aprilasia.com', recipient: 'Sathiyavani', time: 'Friday', receivedLabel: 'Friday at 08:54', category: 'si_request', status: 'complete', body: `Hi Sathiyavani

Please find Shipping instruction for 5RCY-51168.

POL: SINGAPORE
POD: MOMBASA, KENYA

Shipper:
APRIL FINE PAPER TRADING (MIDDLE EAST) FZE
#813, 4 EA, DUBAI AIRPORT FREE ZONE
P.O. BOX: 293775, DUBAI, UNITED ARAB EMIRATES

Consignee:
NAGAPPA EXPORTS
NEW NO : 23, L-BLOCK, 17TH STREET
ANNA NAGAR EAST
CHENNAI, TAMIL NADU 600102
GST NO - 33AACFN6792L1ZU

Notify Party:
NAGAPPA EXPORTS
NEW NO : 23, L-BLOCK, 17TH STREET
ANNA NAGAR EAST
CHENNAI, TAMIL NADU 600102
GST NO - 33AACFN6792L1ZU

Description of Goods:
1X20'GP
UNCOATED WOODFREE PAPER IN REAMS
H.S.CODE: 48025700
GROSS WT: 21,707 KG

Shipping line: OA TERM
Documents Required:
1) 3 Original invoice
2) 3 Packing list
3) 3 Original BL + 3 N/N
Please revert with draft BL once available.`, attachments: [] },
    { id: 'email_147', subject: '18_01_2026 - UPDATE SUMMARY VISION 202 V.002', sender: 'hr@aprilasia.com', recipient: 'Operations Team', time: 'Friday', receivedLabel: 'Friday at 07:31', category: 'general', status: 'complete', body: 'Dear Team,\n\nPlease find attached the list of outstanding BL (BDP SG). Kindly action the pending items.\n\nRegards,\nDocumentation', attachments: [] }
    ,
    { id: 'email_002', subject: 'RE_ LOCAL CHARGES FOB - KARGOSMAR - 5AKR-61849 - TELEX RELEASE CHARGES', sender: 'nirmala@fujitogrp.com', recipient: 'Operations Team', time: 'Thursday', receivedLabel: 'Thursday at 15:22', category: 'invoice_query', status: 'complete', body: `Hi,

Query on invoice 5250075931: is the THC / local charge included or billed separately? Please advise the breakdown.

Best Regards,
Najiha Nur Hanna
Shipping Documentation
DID : +971 04 4938281
APRIL Fine Paper Trading (Middle East) Fze
#813, 4 EA, Dubai Airport Free Zone
P.O. Box : 293775, Dubai, United Arab Emirates
Website : www.aprilasia.com | www.paperone.com`, attachments: [] },
    { id: 'email_254', subject: 'URGENT: Your email storage is full - verify account immediately', sender: 'support@webmail-verify.co', recipient: 'Operations Team', time: 'Thursday', receivedLabel: 'Thursday at 11:09', category: 'spam', status: 'complete', body: 'CONGRATULATIONS!!! Your email address has been selected in our monthly draw. Click here to claim your $1,000 gift card now: http://bit.ly/claim-prize-now', attachments: [] }
  ];
  const categoryLabels = { bl_comparison: 'Bill of Lading Comparison', si_request: 'Shipping Instruction Request', invoice_query: 'Invoice Query', general: 'General', spam: 'Spam' };
  const getSelectedId = () => new URLSearchParams(location.search).get('case') || localStorage.getItem('selectedCase') || 'email_517';
  const getCase = (id = getSelectedId()) => cases.find(item => item.id === id) || cases[0];
  const selectCase = id => localStorage.setItem('selectedCase', id);
  const mismatch = pair => pair && pair[0].normalized != null && pair[1].normalized != null && String(pair[0].normalized) !== String(pair[1].normalized);
  const unresolved = pair => pair && (pair[0].normalized == null || pair[1].normalized == null);
  const getDifferences = item => item.values ? fieldDefinitions.filter(([key]) => mismatch(item.values[key])) : [];
  try {
    const resolutions = JSON.parse(localStorage.getItem('shippingReviewResolutions') || '{}');
    Object.entries(resolutions).forEach(([id, resolution]) => {
      const item = cases.find(entry => entry.id === id);
      if (!item || !resolution.fields) return;
      Object.entries(resolution.fields).forEach(([field, value]) => {
        if (!item.values?.[field]) return;
        item.values[field][0].raw = value;
        item.values[field][0].normalized = value.trim().toUpperCase();
      });
      item.status = 'complete';
    });
  } catch (_) {}
  window.ShippingStore = { fieldDefinitions, categoryLabels, cases, getCase, getSelectedId, selectCase, mismatch, unresolved, getDifferences };
})();
