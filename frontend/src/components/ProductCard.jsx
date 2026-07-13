import React from "react";

/**
 * Product card for a resolved retailer SKU on a room scan overlay.
 *
 * @param {{
 *   product: object,
 *   qtyEstimate?: object,
 *   lineEstimate?: object,
 *   alternates?: object[],
 *   onSelectAlternate?: (product: object) => void,
 *   selected?: boolean,
 * }} props
 */
export default function ProductCard({
  product,
  qtyEstimate,
  lineEstimate,
  alternates = [],
  onSelectAlternate,
  selected = true,
}) {
  if (!product) {
    return null;
  }

  const priceLabel =
    product.price != null
      ? `$${Number(product.price).toFixed(2)}${product.price_unit === "sq_ft" ? "/sq ft" : ""}`
      : "See store for price";

  return (
    <article className={`product-card${selected ? " product-card--selected" : ""}`}>
      {product.image_url && (
        <img src={product.image_url} alt="" className="product-card-image" loading="lazy" />
      )}
      <div className="product-card-body">
        <h4>{product.title}</h4>
        <p className="product-card-price">{priceLabel}</p>
        <p className="muted product-card-stock">
          {product.in_stock ? "In stock" : "Check availability"}
          {product.pickup_available ? " · Pickup available" : ""}
          {product.zip_code ? ` · near ${product.zip_code}` : ""}
        </p>
        {qtyEstimate && (
          <p className="product-card-qty">
            Est. <strong>{qtyEstimate.value}</strong> {qtyEstimate.unit}
            {lineEstimate && (
              <span>
                {" "}
                · ${lineEstimate.low}
                {lineEstimate.high ? `–$${lineEstimate.high}` : ""}
              </span>
            )}
          </p>
        )}
        {product.price_as_of && (
          <p className="muted product-card-disclaimer">Price as of {new Date(product.price_as_of).toLocaleString()}</p>
        )}
        {product.product_url && (
          <a href={product.product_url} target="_blank" rel="noopener noreferrer" className="secondary-button">
            Open at Home Depot
          </a>
        )}
        {alternates.length > 0 && onSelectAlternate && (
          <div className="product-card-alternates">
            <span className="muted">Alternates:</span>
            <ul>
              {alternates.map((alt) => (
                <li key={alt.item_id}>
                  <button type="button" className="text-button" onClick={() => onSelectAlternate(alt)}>
                    {alt.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
}
