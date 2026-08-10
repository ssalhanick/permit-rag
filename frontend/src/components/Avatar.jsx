import React, { useState, useEffect } from "react";
import { API_BASE_URL } from "../api.js";
import { avatarUrlFor, initialsFrom } from "../avatarUtils.js";

/**
 * Avatar — a user's profile photo, falling back to their initials.
 *
 * Renders into whatever sizing class the call site passes (.tt-user-avatar,
 * .profile-sidebar-avatar, …). Those classes are fixed-size circles with a
 * gradient background; styles.css gives each one an `img` rule so the photo
 * fills the same circle and the gradient stays as the initials backdrop.
 *
 * @param {object} props
 * @param {{id?: string, user_id?: string, username?: string, email?: string,
 *          avatar_updated_at?: string|null}} props.user
 * @param {string} [props.className] - sizing/shape class for the slot
 * @param {string} [props.fallback] - text to derive initials from when the user
 *        has no username (e.g. a business name)
 */
export default function Avatar({ user, className = "", fallback, ...rest }) {
  const url = avatarUrlFor(user, API_BASE_URL);
  const [failed, setFailed] = useState(false);

  // A new URL is a new image; without this, one broken photo would keep the
  // fallback pinned even after the user uploads a working replacement.
  useEffect(() => setFailed(false), [url]);

  const initials = initialsFrom(user?.username || fallback || user?.email);

  if (!url || failed) {
    return (
      <div className={className} aria-hidden="true" {...rest}>
        {initials}
      </div>
    );
  }

  return (
    <div className={className} {...rest}>
      <img
        src={url}
        alt=""
        // Decorative: every slot sits next to the username as text, so naming
        // the user again here would just be duplicate noise for a screen reader.
        aria-hidden="true"
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </div>
  );
}
