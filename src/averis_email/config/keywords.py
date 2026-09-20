"""Edit aliases here to support new document labels (case insensitive)."""

FOCUS_FIELDS = (
    "shipper", "consignee", "notify_party", "port_of_loading",
    "port_of_discharge", "container_count", "gross_weight_kg",
)

KEYWORD_ALIASES = {
    "shipper": ("Shipper", "Shipper/Exporter", "Shipper (Principal or Seller)"),
    "consignee": ("Consignee", "Consignee (Non-Negotiable)", "To the Order of"),
    "notify_party": ("Notify", "Notify Party"),
    "port_of_loading": ("POL", "Port of Loading", "Load Port"),
    "port_of_discharge": ("POD", "Discharge Port", "Port of Discharge"),
    "container_count": ("Container Count", "Total Containers", "No. of Containers", "No. of Containers or Packages"),
    "gross_weight_kg": (
        "Gross Wt (kgs)", "Gross Weight (KG)", "Gross Weight毛重(KGS)",
        "Total Gross Weight", "Gross Weight",
    ),
    "vessel": ("Vessel Name", "Ocean Vessel", "Vessel"),
    "voyage": ("Voyage", "Voy. No."),
    "goods_description": ("Commodity", "Description of Goods", "Description"),
    "booking_reference": ("Booking Ref", "Booking No.", "Booking Reference"),
    "hs_code": ("HS Code",),
    "oc_number": ("OC No.",),
    "bl_number": ("Bill of Lading No.", "B/L No.", "B/L Number"),
    # Boundary-only labels prevent preceding values from swallowing table rows.
    "container_number": ("Container No.",),
}
