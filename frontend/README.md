# Shipping Verification UI

A zero-dependency, Gmail-inspired frontend prototype for the hackathon's Person 5 scope:

- inbox classification and processing status;
- seven-field SI-versus-draft-BL comparison;
- side-by-side source evidence;
- human review, correction, retry, and continuation;
- clean-match, mismatch, uncertain, and processing-error demo states.

## Modules

- `index.html` - email-style Work Queue, classification, filtering, and workflow routing;
- `message.html` - the original email body, attachments, and automated outcome;
- `comparison.html` - the seven-field SI-versus-BL result;
- `evidence.html` - side-by-side source traceability;
- `review.html` - human correction and retry workflow;
- `activity.html` - processing stages, exceptions, and evidence coverage.

The selected case is preserved between modules through the URL and browser storage.

## Preview locally

Serve the `dist` folder with any static file server. For example:

```bash
python3 -m http.server 4173 --directory dist
```

Then open `http://127.0.0.1:4173`.

## Connect the backend

The demo cases in `dist/data.js` use representative records from the organiser's supplied bundle and follow the shared field names from the project brief. Replace the `cases` array with data returned by the team API, or generate `data.js` from an API response during integration.

Each comparison case should include:

```js
{
  id: "EM-1048",
  subject: "Check draft BL",
  sender: "ops@example.com",
  time: "09:42",
  category: "document_comparison",
  status: "complete", // or "review"
  siFile: "SI_1048.pdf",
  blFile: "Draft_BL_1048.pdf",
  processingTime: "2.3s",
  values: {
    container_count: [
      {
        file_path: "SI_1048.pdf",
        page_number: 1,
        source_text: "CONTAINER QUANTITY: 3 X 40HC",
        raw: "3 x 40HC",
        normalized: 3
      },
      {
        file_path: "Draft_BL_1048.pdf",
        page_number: 2,
        source_text: "NO. OF CONTAINERS: 4 X 40HC",
        raw: "4 x 40HC",
        normalized: 4
      }
    ]
  }
}
```

Provide all seven keys under `values`: `shipper`, `consignee`, `notify_party`, `port_of_loading`, `port_of_discharge`, `container_count`, and `gross_weight_kg`.

The UI compares normalized values only and always displays raw values and source evidence. No evidence is fabricated when the backend does not provide it.
