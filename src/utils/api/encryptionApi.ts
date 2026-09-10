import { invoke } from "@tauri-apps/api/core";

/**
 * Encryption API for Tauri commands
 * Handles passphrase setup and unlock for SQLCipher database encryption.
 * No keychain caching - user must re-enter passphrase on every session (PHI requirement).
 */
export const encryptionApi = {
  /**
   * Check if encryption has been set up (database file exists)
   */
  hasSetup: async () => {
    try {
      return await invoke("has_encryption_setup");
    } catch (error) {
      console.error("Error checking encryption setup:", error);
      return false;
    }
  },

  /**
   * Check if database file exists
   */
  hasDatabase: async () => {
    try {
      return await invoke("has_database");
    } catch (error) {
      console.error("Error checking database:", error);
      return false;
    }
  },

  /**
   * Check if passphrase is cached in keychain
   * Always returns false since we don't use keychain caching (PHI requirement)
   */
  hasKeychain: async () => {
    try {
      return await invoke("has_keychain_entry");
    } catch (error) {
      console.error("Error checking keychain:", error);
      return false;
    }
  },

  /**
   * Get complete encryption status
   */
  getStatus: async () => {
    try {
      return await invoke("get_encryption_status");
    } catch (error) {
      console.error("Error getting encryption status:", error);
      return {
        has_setup: false,
        has_database: false,
        has_keychain: false,
      };
    }
  },

  /**
   * Set up encryption with a new passphrase
   * @param {string} passphrase - User's passphrase (min 12 characters)
   * @returns {string} Hex-encoded passphrase to pass to start_server_command
   */
  setup: async (passphrase) => {
    return await invoke("setup_encryption", { passphrase });
  },

  /**
   * Unlock with passphrase
   * @param {string} passphrase - User's passphrase
   * @returns {string} Hex-encoded passphrase to pass to start_server_command
   */
  unlock: async (passphrase) => {
    return await invoke("unlock_with_passphrase", { passphrase });
  },

  /**
   * Change passphrase (not yet implemented)
   */
  changePassphrase: async (oldPassphrase, newPassphrase) => {
    return await invoke("change_passphrase", {
      oldPassphrase: oldPassphrase,
      newPassphrase: newPassphrase,
    });
  },

  /**
   * Clear keychain (no-op since we don't use keychain)
   */
  clearKeychain: async () => {
    return await invoke("clear_keychain");
  },
};

/**
 * Calculate passphrase strength.
 *
 * Unicode-aware: Persian (and other non-Latin) passphrases are scored on
 * length, multi-word structure and script mixing instead of ASCII-only
 * upper/lower-case rules that can never be satisfied by Persian text.
 *
 * @param {string} passphrase
 * @returns {object} - { score: 0-4, strength: string, feedback: string[] }
 */
export const calculatePassphraseStrength = (passphrase) => {
  let score = 0;
  const feedback = [];

  // Length is the dominant factor — a 16-character Persian phrase is a
  // strong passphrase even without digits or symbols.
  if (passphrase.length >= 12) score += 1;
  else feedback.push("حداقل ۱۲ نویسه وارد کنید");

  if (passphrase.length >= 16) score += 1;
  else if (passphrase.length >= 12)
    feedback.push("عبارت عبور ۱۶ نویسه‌ای یا بلندتر امن‌تر است");

  // Character diversity: mixed case (Latin scripts) or mixing two scripts
  // (e.g. Persian + Latin) both raise guessing cost.
  const hasLower = /\p{Ll}/u.test(passphrase);
  const hasUpper = /\p{Lu}/u.test(passphrase);
  const scriptPatterns = [
    /\p{Script=Latin}/u,
    /\p{Script=Arabic}/u,
    /\p{Script=Cyrillic}/u,
    /\p{Script=Greek}/u,
  ];
  const scriptCount = scriptPatterns.filter((pattern) =>
    pattern.test(passphrase),
  ).length;
  if ((hasLower && hasUpper) || scriptCount >= 2) score += 1;
  else
    feedback.push("ترکیب دو زبان یا حروف کوچک و بزرگ، امنیت را بالا می‌برد");

  if (/\p{Nd}/u.test(passphrase)) score += 1;
  else feedback.push("افزودن عدد توصیه می‌شود");

  if (/[^\p{L}\p{Nd}\s]/u.test(passphrase)) score += 1;
  else feedback.push("افزودن نشانه (مانند - یا ! یا @) توصیه می‌شود");

  // Multi-word passphrases ("correct horse battery staple") get structure
  // credit even in single-script languages.
  if (passphrase.trim().split(/\s+/).length >= 3) score += 1;
  else feedback.push("عبارت عبور چندکلمه‌ای انتخاب کنید");

  // Cap at 4
  const finalScore = Math.min(score, 4);

  let strength = "ضعیف";
  if (finalScore >= 4) strength = "قوی";
  else if (finalScore >= 3) strength = "خوب";
  else if (finalScore >= 2) strength = "متوسط";

  return {
    score: finalScore,
    strength,
    feedback: feedback.length > 0 ? feedback : ["عبارت عبور مناسبی است"],
  };
};
