# Walkthrough: Ingest a single file end-to-end

This walkthrough takes an operator from a freshly-configured ADME instance to **one `File.Generic` record** discoverable in Search. You'll upload a file, build a manifest that references it, submit the manifest through the Workflow Service, and verify the result. Plan on ~2 minutes of clicking plus 30–90 seconds of OSDU-side processing.

## Prerequisites

Before you start, confirm:

- **Instance Configuration done.** Endpoint, tenant, client, partition, auth method, and token scope are saved. See [Instance Configuration](../../app/pages/1_⚙️_Instance_Configuration.py).
- **Signed in.** The welcome page (`app/main.py`) shows a green "connection ready" indicator; **Test Connection** succeeds for the partition.
- **At least one legal tag visible** on the **🏷️ Legal Tags** page. If none, create one there first.
- **At least one ACL group visible** on the **🔑 Entitlements** page. You need its full `data.*@partition.dataservices.energy` form for the manifest.
- A small (< 100 MB) test file on disk — any `.txt`, `.csv`, or `.las` will do.

If any of these are missing, the dropdowns in Step 2 will be empty and the walkthrough won't complete.

---

## Step 1 — Upload a file

1. From the sidebar, open the **Ingest** group → **📂 File**.
2. Fill in:
   - **Display name** — human-readable, e.g. `TNO sample well log`.
   - **Description** — one-line summary; optional but recommended.
3. Click **Browse files** and pick your test file.
4. Click **Upload**.

The page runs the three-phase OSDU File Service v2 flow (signed URL → blob PUT → metadata POST). On success you'll see:

```
✅ Uploaded as record `opendes:dataset--File.Generic:abc123…`
```

…plus the **FileSource** value (an internal storage path) shown below it. Both are also written to the in-session upload history — that's what the Manifest Builder reads in Step 2.

`[Screenshot: File Upload page after a successful upload showing record id and FileSource]`

> **Why two values?** `FileSource` is the storage-side handle the manifest needs in `data.DatasetProperties.FileSourceInfo.FileSource`. The record id is the OSDU id of the metadata record. They are unrelated tokens — keep both if you intend to reference this upload later (see [Paste mode](#paste-mode-alternative)).

---

## Step 2 — Build the manifest

1. From the sidebar, open the **Ingest** group → **📄 Manifest**.
2. Expand **🛠️ Build manifest**.
3. Leave the pick-mode toggle on **📂 From recent uploads** (the default).
4. In the **Recent uploads** selectbox, choose the file you just uploaded. The display name and description carry over automatically.
5. Pick:
   - **Legal tag** — from your partition's tags.
   - **ACL owner** — full group address.
   - **ACL viewer** — full group address (often the same as owner for v1).
6. Click **Generate**.

`[Screenshot: Manifest Builder expander expanded with recent-uploads selectbox and ACL pickers filled]`

The **Manifest editor** below the expander pre-fills with valid JSON — a single `osdu:wks:dataset--File.Generic:1.0.0` record wrapped in the Workflow Service `executionContext` envelope. You can review or hand-edit before submitting.

A minimal generated manifest looks like:

```json
{
  "executionContext": {
    "Payload": {
      "AppKey": "adme-ingestion-tool",
      "data-partition-id": "opendes"
    },
    "manifest": {
      "kind": "osdu:wks:Manifest:1.0.0",
      "Datasets": [
        {
          "kind": "osdu:wks:dataset--File.Generic:1.0.0",
          "acl": { "owners": ["..."], "viewers": ["..."] },
          "legal": { "legaltags": ["..."], "otherRelevantDataCountries": ["US"], "status": "compliant" },
          "data": {
            "Name": "TNO sample well log",
            "Description": "...",
            "DatasetProperties": {
              "FileSourceInfo": { "FileSource": "...", "Name": "TNO sample well log" }
            }
          }
        }
      ]
    }
  }
}
```

---

## Step 3 — Submit

1. With the manifest in the editor, click **Validate & Ingest**.
2. Watch the **Status** panel below — it shows the run id and polls the Workflow Service.

Workflow submission typically takes **5–15 seconds** server-side; the page timeout is 30 seconds. A successful run ends at status `finished` (or `succeeded` depending on the partition's DAG version).

`[Screenshot: Status panel showing finished workflow run with run id and elapsed time]`

If the workflow fails, the panel surfaces the error message and correlation id from the Workflow Service. Most failures at this stage are legal-tag or ACL mismatches — see [Troubleshooting](#troubleshooting).

---

## Step 4 — Verify

1. From the sidebar, open the **Operate** group → **🔍 Search**.
2. Set **Kind** to `osdu:wks:dataset--File.Generic:1.0.0` (or use a wildcard like `*:*:dataset--File.Generic:*`).
3. Leave the query blank or type `data.Name:"TNO sample well log"`.
4. Click **Search**.

Your new record should appear. **Indexing lag is real** — OSDU's Search index typically catches up 30–60 seconds after the workflow finishes. If the record isn't there, wait and re-search.

`[Screenshot: Search page showing the new File.Generic record with display name and record id]`

Click the record to expand the full document and confirm `data.DatasetProperties.FileSourceInfo.FileSource` matches the value from Step 1.

---

## Paste mode (alternative)

If your upload happened in a previous Streamlit session (or outside the app entirely), the **Recent uploads** picker will not show it. Instead:

1. On the **📄 Manifest** page, expand **🛠️ Build manifest**.
2. Switch the pick-mode toggle to **✏️ Paste manually**.
3. Provide **both**:
   - **FileSource** — the storage path from the original upload's success message.
   - **File record id** — the `opendes:dataset--File.Generic:…` id.
4. Fill display name, description, legal tag, and ACL groups as usual, then **Generate**.

> Neither value is recoverable from the other. If you only have one, you'll have to either re-upload the file or query Search/Storage for the missing piece.

---

## Troubleshooting

- **Legal tag not in dropdown.** Open **🏷️ Legal Tags** — if the tag isn't listed, create it; if it is listed but missing from Manifest, refresh the page (the dropdown reads on page load).
- **ACL group not in dropdown.** Open **🔑 Entitlements** — confirm your principal is a member of the group. The Builder shows only groups visible to the signed-in user.
- **Workflow timeout (30 s).** Submission accepted but no terminal status yet. Open the run id in OSDU's workflow UI, or re-poll by re-submitting (idempotent given a unique run id will be issued).
- **Search index lag.** Wait 30–60 seconds after `finished` and re-run the query. If still missing after 2 minutes, fetch by record id directly from **Search** (record-fetch panel) to confirm the record exists in Storage.
- **Validator complaint in editor.** The Builder always emits valid JSON; if you hand-edited and broke it, click **Generate** again to reset.

---

See also: [Operator Flow](../../README.md#operator-flow) · [Manifest Builder contract](../../.squad/decisions/inbox/satya-manifest-builder-contract.md)
