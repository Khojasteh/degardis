### Assets

`content.assets` selects supporting files that are neither scripts nor guides. Selected assets are copied unchanged, including Markdown assets, to the same path they have in the source.

An inline reference links an asset:

```markdown
Use [[asset:template.docx]] for the final document.
```

The target is the asset's source-relative path, or any trailing part of it made of whole segments; one that ends more than one selected asset is refused until it names one. A selected asset with no inline reference warns.

The bundle may also contain generated support assets: PNG icon roles when `interface.icon` is set, and an instruction-register asset when the bundle contains at least one principle or guide page.
