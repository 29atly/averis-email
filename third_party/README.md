# Third-party source checkouts

`PaddleOCR/` is a local, ignored clone of
<https://github.com/PaddlePaddle/PaddleOCR.git>. The integration was developed
against commit `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf`.

Recreate the checkout with:

```bash
git clone --depth 1 https://github.com/PaddlePaddle/PaddleOCR.git third_party/PaddleOCR
```

The application installs PaddleOCR through the `ocr` optional dependency; this
checkout is retained as the inspected upstream source rather than imported by
application code.
