/**
 * taskStorage.js — per-project task list, persisted to localStorage.
 *
 * Shared by TasksPage, DashboardPage, and ProjectDashboardPage so a task
 * added on any surface shows up on the others and survives a reload.
 */

const STORAGE_PREFIX = "permit_rag_tasks_";

/**
 * Build the localStorage key for a project's task list.
 *
 * @param {string} projectId
 * @returns {string}
 */
export function taskStorageKey(projectId) {
  return `${STORAGE_PREFIX}${projectId}`;
}

/**
 * Load a project's tasks from localStorage.
 *
 * @param {string} projectId
 * @returns {object[]}
 */
export function loadProjectTasks(projectId) {
  if (!projectId || typeof localStorage === "undefined") {
    return [];
  }
  const raw = localStorage.getItem(taskStorageKey(projectId));
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Persist a project's full task list to localStorage.
 *
 * @param {string} projectId
 * @param {object[]} tasks
 */
export function saveProjectTasks(projectId, tasks) {
  if (!projectId || typeof localStorage === "undefined") {
    return;
  }
  localStorage.setItem(taskStorageKey(projectId), JSON.stringify(tasks || []));
}
