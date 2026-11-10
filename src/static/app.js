document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const messageDiv = document.getElementById("message");
  const accountMessage = document.getElementById("account-message");
  const signedOut = document.getElementById("signed-out");
  const signedIn = document.getElementById("signed-in");
  const adminContainer = document.getElementById("admin-container");
  let currentUser = null;

  function element(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    let result;
    try {
      result = await response.json();
    } catch {
      throw new Error("The server returned an invalid response.");
    }
    if (!response.ok) {
      const error = new Error(
        result.detail || "The request could not be completed."
      );
      error.status = response.status;
      throw error;
    }
    return result;
  }

  function showMessage(target, text, type = "info") {
    target.textContent = text;
    target.className = `message ${type}`;
    target.classList.remove("hidden");
  }

  async function fetchActivities() {
    try {
      const activities = await api("/activities");
      activitiesList.replaceChildren();
      activitySelect.replaceChildren(new Option("-- Select an activity --", ""));

      Object.entries(activities).forEach(([name, details]) => {
        const card = element("div", "activity-card");
        card.append(
          element("h4", "", name),
          element("p", "", details.description),
          element("p", "", `Schedule: ${details.schedule}`),
          element(
            "p",
            "",
            `Availability: ${details.max_participants - details.participant_count} spots left`
          )
        );

        if (details.participants.length > 0) {
          const participants = element("div", "participants-container");
          participants.append(element("h5", "", "Participants:"));
          const list = element("ul", "participants-list");
          details.participants.forEach((email) => {
            const item = element("li");
            item.append(element("span", "participant-email", email));
            const canManage =
              currentUser &&
              (currentUser.role === "admin" ||
                currentUser.role === "activity_manager");
            if (canManage || (currentUser && email === currentUser.email)) {
              const removeButton = element("button", "delete-btn", "Unregister");
              removeButton.type = "button";
              removeButton.addEventListener("click", () => unregister(name, email));
              item.append(removeButton);
            }
            list.append(item);
          });
          participants.append(list);
          card.append(participants);
        }

        activitiesList.append(card);
        activitySelect.add(new Option(name, name));
      });
    } catch (error) {
      activitiesList.replaceChildren(
        element("p", "", `Failed to load activities: ${error.message}`)
      );
    }
  }

  async function loadAdminUsers() {
    if (currentUser?.role !== "admin") {
      adminContainer.classList.add("hidden");
      return;
    }
    adminContainer.classList.remove("hidden");
    const usersContainer = document.getElementById("admin-users");
    try {
      const users = await api("/admin/users");
      usersContainer.replaceChildren();
      users.forEach((user) => {
        const row = element("div", "admin-user");
        row.append(element("p", "", `${user.name} (${user.email}) — ${user.status}`));
        const controls = element("div", "admin-user-controls");
        const status = element("select");
        status.setAttribute("aria-label", `Status for ${user.email}`);
        ["pending", "approved", "rejected", "deactivated"].forEach((value) =>
          status.add(new Option(value, value, false, value === user.status))
        );
        const role = element("select");
        role.setAttribute("aria-label", `Role for ${user.email}`);
        ["student", "activity_manager", "admin"].forEach((value) =>
          role.add(
            new Option(value.replace("_", " "), value, false, value === user.role)
          )
        );
        const save = element("button", "", "Save");
        save.type = "button";
        save.addEventListener("click", async () => {
          try {
            await api(`/admin/users/${user.id}`, {
              method: "PATCH",
              body: JSON.stringify({ status: status.value, role: role.value }),
            });
            showMessage(accountMessage, `Updated access for ${user.email}.`, "success");
            await loadAdminUsers();
          } catch (error) {
            showMessage(accountMessage, error.message, "error");
          }
        });
        controls.append(status, role, save);
        row.append(controls);
        usersContainer.append(row);
      });
    } catch (error) {
      usersContainer.replaceChildren(element("p", "error", error.message));
    }
  }

  async function loadAccount() {
    try {
      currentUser = await api("/me");
      signedOut.classList.add("hidden");
      signedIn.classList.remove("hidden");
      document
        .getElementById("signup-container")
        .classList.toggle("hidden", currentUser.role !== "student");
      document.getElementById("account-summary").textContent =
        `${currentUser.name} (${currentUser.email}) — ${currentUser.role}`;
      document.getElementById("profile-name").value = currentUser.name;
      document.getElementById("profile-grade").value = currentUser.grade;
    } catch (error) {
      currentUser = null;
      signedOut.classList.remove("hidden");
      signedIn.classList.add("hidden");
      adminContainer.classList.add("hidden");
      document.getElementById("signup-container").classList.add("hidden");
      if (error.status !== 401) {
        showMessage(accountMessage, error.message, "error");
        console.error("Error loading account:", error);
      }
    }
    await loadAdminUsers();
  }

  async function unregister(activity, email) {
    try {
      const query =
        currentUser.role === "admin" || currentUser.role === "activity_manager"
          ? `?email=${encodeURIComponent(email)}`
          : "";
      const result = await api(
        `/activities/${encodeURIComponent(activity)}/unregister${query}`,
        { method: "DELETE" }
      );
      showMessage(messageDiv, result.message, "success");
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, "error");
    }
  }

  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      event.target.reset();
      showMessage(accountMessage, "Signed in.", "success");
      await loadAccount();
      await fetchActivities();
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
    }
  });

  document.getElementById("register-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      name: document.getElementById("register-name").value,
      email: document.getElementById("register-email").value,
      grade: document.getElementById("register-grade").value,
      password: document.getElementById("register-password").value,
    };
    try {
      const result = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      event.target.reset();
      showMessage(accountMessage, result.message, "success");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
    }
  });

  document.getElementById("profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      currentUser = await api("/me", {
        method: "PATCH",
        body: JSON.stringify({
          name: document.getElementById("profile-name").value,
          grade: document.getElementById("profile-grade").value,
        }),
      });
      document.getElementById("account-summary").textContent =
        `${currentUser.name} (${currentUser.email}) — ${currentUser.role}`;
      showMessage(accountMessage, "Profile updated.", "success");
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
    }
  });

  document.getElementById("logout-button").addEventListener("click", async () => {
    try {
      await api("/auth/logout", { method: "POST" });
      currentUser = null;
      showMessage(accountMessage, "Signed out.", "success");
      await loadAccount();
      await fetchActivities();
    } catch (error) {
      showMessage(accountMessage, error.message, "error");
    }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api(
        `/activities/${encodeURIComponent(activitySelect.value)}/signup`,
        { method: "POST" }
      );
      showMessage(messageDiv, result.message, "success");
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, "error");
    }
  });

  loadAccount().then(fetchActivities);
});
