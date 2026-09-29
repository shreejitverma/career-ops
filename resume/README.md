# Resume variants

Tailored resume builds, one folder per target track and length.
Each folder holds the editable Word source and the PDF that gets submitted.

| Variant | Files |
| :--- | :--- |
| `quant/one-page` | `Shreejit Verma Resume.docx`, `Shreejit Verma Resume.pdf` |
| `quant/two-page` | `Shreejit Verma Resume.docx`, `Shreejit Verma Resume.pdf` |
| `fpga/one-page` | `Shreejit Verma Resume.docx`, `Shreejit Verma Resume.pdf` |
| `fpga/two-page` | `Shreejit Verma Resume.docx`, `Shreejit Verma Resume.pdf` |

The job board (`node jobboard/jobboard.mjs serve`) discovers every `<track>/<length>/*.pdf` here.
When you confirm an application it asks which variant you sent, records it on the job and in the new command-center tracker (`resume:`), and links the PDF for quick attaching.

`cv.md` stays the canonical source of facts for generated CVs; these files are finished documents and are never read as a content source.

Fork-local: `resume/` is declared in `config/local-paths.txt`, so `update-system.mjs` never touches it.
Keep the repository private: these files carry contact details.
