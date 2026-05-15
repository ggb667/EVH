# Stockroom product UUID map

Source: `stockroom.instinctvet.com.har`

This file captures the product mapping that was visible in the HAR capture. At present, the HAR excerpt contains one full product lookup/update cycle.

## Product

| product_id | code | label | supplier_ids | buying_unit_id | selling_unit_id |
| --- | --- | --- | --- | --- | --- |
| `5ce72b86-ab11-4892-870f-190ee7b29ed0` | `S-786909` | `Zycortal Suspension 25mg/ml 4ml` | `1f6e2359-3083-4585-8ee8-b520223b4c62`, `d2c97d7b-d914-490e-a2b7-f17033daf35d` | `701177c1-29dc-4026-a8d3-9839529e004b` | `701177c1-29dc-4026-a8d3-9839529e004b` |

## Notes

- The `load_global_product` reply showed the product with no suppliers attached yet.
- The `update_global_product` reply showed the same product with suppliers populated.
- The update payload used `sender_id: product-catalog` and included the supplier UUIDs above.
- If a larger mapping is needed, the same extraction pattern can be repeated against additional HAR captures.
