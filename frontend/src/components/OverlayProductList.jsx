import React from "react";
import ProductCard from "./ProductCard.jsx";

/**
 * List of product cards from design-intent overlays.
 *
 * @param {{
 *   overlays: object[],
 *   onSelectProduct?: (overlayIndex: number, product: object) => void,
 * }} props
 */
export default function OverlayProductList({ overlays, onSelectProduct }) {
  const withProducts = (overlays || []).filter((o) => o.product_ref);
  if (!withProducts.length) {
    return null;
  }

  return (
    <section className="overlay-product-list" aria-label="Suggested products">
      <h4>Suggested products</h4>
      <p className="muted">Prices and availability change — confirm in store.</p>
      <div className="overlay-product-grid">
        {withProducts.map((overlay, index) => (
          <ProductCard
            key={`${overlay.product_ref.item_id}-${index}`}
            product={overlay.product_ref}
            qtyEstimate={overlay.qty_estimate}
            lineEstimate={overlay.line_estimate}
            alternates={overlay.product_alternates}
            onSelectAlternate={
              onSelectProduct
                ? (product) => onSelectProduct(index, product)
                : null
            }
          />
        ))}
      </div>
    </section>
  );
}
