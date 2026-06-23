/**
 * AddressAutocomplete.jsx — Mapbox address autocomplete (Sprint 5)
 * ----------------------------------------------------------------
 * Provides a typeahead address input using the Mapbox Search Box API.
 * Restricted to the DFW metro area via proximity bias and bbox.
 *
 * Props:
 *   value      — controlled string value
 *   onChange   — called with the new string as user types
 *   onSelect   — called with { address, municipality } when a suggestion is picked
 *   placeholder — input placeholder text
 *   id         — input element id
 *
 * Environment:
 *   VITE_MAPBOX_TOKEN — Mapbox public access token (pk.*)
 *   Falls back to a no-autocomplete plain text input if token is not set.
 *
 * Future: swap Mapbox token for Google Maps API key when LLC is established.
 *   See docs/backlog.md — "Blocking Condition for Google Maps Upgrade"
 */

import React, { useCallback, useEffect, useRef, useState } from "react";

const MAPBOX_TOKEN = import.meta.env?.VITE_MAPBOX_TOKEN || "";

// DFW metro bounding box [min_lng, min_lat, max_lng, max_lat]
const DFW_BBOX = "-97.7,32.4,-96.2,33.4";
// DFW center for proximity bias
const DFW_PROXIMITY = "-96.797,32.777";

const DEBOUNCE_MS = 300;
const MIN_CHARS = 3;

function generateUUID() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Fetch Mapbox suggestions for a query string.
 * Uses the Mapbox Search Box suggest endpoint with required session_token.
 */
async function fetchSuggestions(query, sessionToken) {
  if (!MAPBOX_TOKEN || query.length < MIN_CHARS) return [];
  const url = new URL("https://api.mapbox.com/search/searchbox/v1/suggest");
  url.searchParams.set("q", query);
  url.searchParams.set("access_token", MAPBOX_TOKEN);
  url.searchParams.set("session_token", sessionToken);
  url.searchParams.set("types", "address");
  url.searchParams.set("country", "US");
  url.searchParams.set("bbox", DFW_BBOX);
  url.searchParams.set("proximity", DFW_PROXIMITY);
  url.searchParams.set("limit", "5");
  try {
    const resp = await fetch(url.toString());
    if (!resp.ok) return [];
    const body = await resp.json();
    return body.suggestions || [];
  } catch {
    return [];
  }
}

/**
 * Retrieve the full feature for a Mapbox suggestion (to get coordinates).
 * Returns { full_address, municipality } or null.
 */
async function retrieveSuggestion(mapboxId, sessionToken) {
  if (!MAPBOX_TOKEN || !mapboxId) return null;
  const url = new URL("https://api.mapbox.com/search/searchbox/v1/retrieve/" + mapboxId);
  url.searchParams.set("access_token", MAPBOX_TOKEN);
  url.searchParams.set("session_token", sessionToken);
  try {
    const resp = await fetch(url.toString());
    if (!resp.ok) return null;
    const body = await resp.json();
    const feat = body.features?.[0];
    if (!feat) return null;
    const ctx = feat.properties?.context || {};
    // Try to extract city name for a hint
    const place = ctx.place?.name || ctx.locality?.name || "";
    return {
      address: feat.properties?.full_address || feat.properties?.name || "",
      municipality: place.toLowerCase().replace(/\s+/g, "-") || null,
    };
  } catch {
    return null;
  }
}

export default function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder = "1234 Main St, Dallas, TX 75201",
  id = "address",
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sessionToken, setSessionToken] = useState(() => generateUUID());
  const debounceRef = useRef(null);
  const containerRef = useRef(null);

  // Debounced suggestion fetch
  const fetchDebounced = useCallback((query, token) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      const results = await fetchSuggestions(query, token);
      setSuggestions(results);
      setOpen(results.length > 0);
      setLoading(false);
    }, DEBOUNCE_MS);
  }, []);

  const handleInput = (e) => {
    const val = e.target.value;
    onChange(val);
    if (val.length >= MIN_CHARS) {
      fetchDebounced(val, sessionToken);
    } else {
      setSuggestions([]);
      setOpen(false);
    }
  };

  const handleSelect = async (suggestion) => {
    const label = suggestion.full_address || suggestion.name || "";
    onChange(label);
    setOpen(false);
    setSuggestions([]);
    // Retrieve full feature for municipality hint
    const detail = await retrieveSuggestion(suggestion.mapbox_id, sessionToken);
    // Cycle the session token after retrieve is complete
    setSessionToken(generateUUID());
    if (onSelect) {
      onSelect({
        address: detail?.address || label,
        municipality: detail?.municipality || null,
      });
    }
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // If no token, render a plain input with a note
  if (!MAPBOX_TOKEN) {
    return (
      <div>
        <input
          id={id}
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="street-address"
          aria-label="Project address"
        />
        <small className="muted">
          Address autocomplete: set VITE_MAPBOX_TOKEN in frontend/.env to enable.
        </small>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="autocomplete-container" aria-haspopup="listbox">
      <input
        id={id}
        type="text"
        value={value || ""}
        onChange={handleInput}
        placeholder={placeholder}
        autoComplete="off"
        aria-autocomplete="list"
        aria-controls="address-suggestions"
        aria-expanded={open}
        aria-label="Project address"
        onFocus={() => suggestions.length > 0 && setOpen(true)}
      />
      {loading && <span className="autocomplete-loading" aria-live="polite">…</span>}
      {open && suggestions.length > 0 && (
        <ul
          id="address-suggestions"
          role="listbox"
          className="autocomplete-dropdown"
          aria-label="Address suggestions"
        >
          {suggestions.map((s) => {
            const label = s.full_address || s.name || s.place_formatted || "";
            return (
              <li key={s.mapbox_id} role="option" aria-selected="false">
                <button
                  type="button"
                  className="autocomplete-option"
                  onClick={() => handleSelect(s)}
                >
                  <span className="autocomplete-primary">{s.name}</span>
                  {s.place_formatted && (
                    <span className="autocomplete-secondary">{s.place_formatted}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
