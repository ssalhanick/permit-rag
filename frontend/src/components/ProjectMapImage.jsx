import React from "react";

const MAPBOX_TOKEN = import.meta.env?.VITE_MAPBOX_TOKEN || "";

/**
 * Static Mapbox map thumbnail for a project's address, using the same
 * VITE_MAPBOX_TOKEN as AddressAutocomplete. Renders nothing if the token
 * or project coordinates aren't available.
 */
export default function ProjectMapImage({ latitude, longitude, address }) {
  if (!MAPBOX_TOKEN || latitude == null || longitude == null) {
    return null;
  }

  const src =
    `https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/` +
    `pin-s+3b82f6(${longitude},${latitude})/${longitude},${latitude},15,0/480x240@2x` +
    `?access_token=${MAPBOX_TOKEN}`;

  return (
    <img
      src={src}
      alt={address ? `Map of ${address}` : "Project location map"}
      className="w-full max-w-md rounded-md border border-slate-700"
      loading="lazy"
    />
  );
}
