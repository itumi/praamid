document.addEventListener('DOMContentLoaded', () => {
    const getScheduleBtn = document.getElementById('getScheduleBtn'); // Now "Load Available Times"
    const resultsContainer = document.getElementById('resultsContainer');
    const directionSelect = document.getElementById('direction');
    const departureDateInput = document.getElementById('departureDate');
    // numCarsInput removed as we assume 1 car if vehicleRegNr is filled
    // const numCarsInput = document.getElementById('numCars');
    const vehicleRegNrGroup = document.getElementById('vehicleRegNrGroup');
    const vehicleRegNrInput = document.getElementById('vehicleRegNr');
    const numAdultsInput = document.getElementById('numAdults');
    const emailInput = document.getElementById('email');
    const phoneInput = document.getElementById('phone');
    const errorMessagesDiv = document.getElementById('errorMessages');

    const monitoringControlsArea = document.getElementById('monitoringControlsArea');
    const startMonitoringBtn = document.getElementById('startMonitoringBtn');
    const stopMonitoringBtn = document.getElementById('stopMonitoringBtn');
    const monitoringStatusDiv = document.getElementById('monitoringStatus');

    // Global state for monitoring
    let monitoredSlots = [];
    let monitoringIntervalId = null;
    let currentUserDetails = {};

    // Set default date to today
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
    const dd = String(today.getDate()).padStart(2, '0');
    departureDateInput.value = `${yyyy}-${mm}-${dd}`;

    // Vehicle Reg Nr is always visible as per new plan for 1 car booking.
    // No need for special show/hide logic based on numCarsInput anymore.
    // if (numCarsInput && vehicleRegNrGroup) { ... } // This logic is removed.

    if (getScheduleBtn) {
        getScheduleBtn.addEventListener('click', fetchSchedule);
    }

    async function fetchSchedule() {
        const direction = directionSelect.value;
        const date = departureDateInput.value;

        clearMessages();
        resultsContainer.innerHTML = '<p>Loading available times...</p>';
        monitoringControlsArea.style.display = 'none'; // Hide monitoring controls initially

        if (!date) {
            showError('Departure Date is required.');
            resultsContainer.innerHTML = '<p>Please select a Departure Date.</p>';
            return;
        }

        const backendBaseUrl = 'http://localhost:8080';
        const backendUrl = `${backendBaseUrl}/api/get_schedule?direction=${direction}&date=${date}`;

        try {
            const response = await fetch(backendUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                let errorMsg = `Error loading times: ${response.status} ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    errorMsg += ` - ${errorData.error || 'Unknown server error'}`;
                } catch (e) {
                    // Ignore if error response is not JSON
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();
            displaySchedule(data, direction, date);

        } catch (error) {
            console.error('Failed to load times:', error);
            resultsContainer.innerHTML = `<p>Failed to load available times. ${error.message}</p>`;
            showError(`Failed to load available times. ${error.message}. Ensure backend is running.`);
        }
    }

    function displaySchedule(scheduleData, direction, departureDate) {
        resultsContainer.innerHTML = ''; // Clear previous results or "Loading..."

        if (!scheduleData || scheduleData.length === 0) {
            resultsContainer.innerHTML = '<p>No trips found for the selected date and direction.</p>';
            monitoringControlsArea.style.display = 'none';
            return;
        }

        const ul = document.createElement('ul');
        ul.classList.add('trip-list');

        scheduleData.forEach(trip => {
            const li = document.createElement('li');
            li.classList.add('trip-item');

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `trip-${trip.event_uid}`;
            checkbox.value = trip.event_uid;
            // Store necessary data directly on the checkbox element for easy retrieval
            checkbox.dataset.eventData = JSON.stringify(trip.original_event_data);
            checkbox.dataset.pricelistCode = (trip.pricelist && trip.pricelist.code) ? trip.pricelist.code : '';
            checkbox.dataset.dtstartUtcIso = trip.dtstart_utc_iso;


            const label = document.createElement('label');
            label.htmlFor = checkbox.id;

            const displayStartTime = trip.startTimeLocal || formatTime(trip.dtstart_utc_iso);
            const displayEndTime = trip.endTimeLocal || formatTime(trip.dtend_utc_iso);
            const carAvailability = (trip.capacities && typeof trip.capacities.sv !== 'undefined') ? trip.capacities.sv : "N/A";
            const shipCode = (trip.ship && trip.ship.code) ? trip.ship.code : "N/A";

            label.innerHTML = ` ${displayStartTime} - ${displayEndTime} (UTC) | Ship: ${shipCode} | Cars: <span class="cars-count">${carAvailability}</span>`;

            if (typeof carAvailability === 'number' && carAvailability > 0) {
                li.classList.add('available');
            } else {
                li.classList.add('unavailable');
                checkbox.disabled = true; // Disable checkbox if no cars available initially
                label.innerHTML += " (Unavailable for monitoring)";
            }

            li.appendChild(checkbox);
            li.appendChild(label);
            ul.appendChild(li);
        });
        resultsContainer.appendChild(ul);
        monitoringControlsArea.style.display = 'block'; // Show monitoring buttons
        stopMonitoringBtn.style.display = 'none'; // Ensure stop is hidden initially
        startMonitoringBtn.style.display = 'inline-block';
    }

    // Add event listeners for new buttons
    if (startMonitoringBtn) {
        startMonitoringBtn.addEventListener('click', startMonitoring);
    }
    if (stopMonitoringBtn) {
        stopMonitoringBtn.addEventListener('click', stopMonitoring);
    }

    function updateMonitoringStatus(message) {
        if (monitoringStatusDiv) {
            monitoringStatusDiv.innerHTML = `<p>${message}</p>`;
        }
        console.log("Monitoring Status:", message);
    }

    function startMonitoring() {
        clearMessages();
        const selectedCheckboxes = document.querySelectorAll('.trip-item input[type="checkbox"]:checked');

        if (selectedCheckboxes.length === 0) {
            showError("Please select at least one time slot to monitor.");
            return;
        }

        const userEmail = emailInput.value.trim();
        const userPhone = phoneInput.value.trim();
        const vehicleRegNr = vehicleRegNrInput.value.trim(); // Assuming 1 car if this is filled
        const numAdults = parseInt(numAdultsInput.value);

        if (!userEmail || !userPhone) {
            showError("Email and Phone Number are required to start monitoring.");
            return;
        }
        if (!vehicleRegNr) { // Assuming vehicle is always booked with this app.
            showError("Vehicle Registration Number is required to start monitoring.");
            return;
        }
         if (isNaN(numAdults) || numAdults < 1) { // Ensure at least 1 adult
            showError("Please enter a valid number of adults (at least 1).");
            return;
        }

        currentUserDetails = { userEmail, userPhone, vehicleRegNr, numAdults, numCars: 1 }; // Store for use in polling

        monitoredSlots = Array.from(selectedCheckboxes).map(cb => {
            return {
                eventUid: cb.value,
                dtstartUtcIso: cb.dataset.dtstartUtcIso,
                originalEventData: JSON.parse(cb.dataset.eventData),
                pricelistCode: cb.dataset.pricelistCode,
                direction: directionSelect.value, // Get current direction
                departureDate: departureDateInput.value // Get current date
            };
        });

        if (monitoringIntervalId) {
            clearInterval(monitoringIntervalId); // Clear existing interval if any
        }

        // Poll every 30 seconds (adjust as needed)
        const POLLING_INTERVAL = 30000;
        monitoringIntervalId = setInterval(pollAllSelectedSlots, POLLING_INTERVAL);

        startMonitoringBtn.style.display = 'none';
        stopMonitoringBtn.style.display = 'inline-block';
        updateMonitoringStatus(`Monitoring ${monitoredSlots.length} time slot(s). Will check every ${POLLING_INTERVAL / 1000} seconds.`);
        pollAllSelectedSlots(); // Initial immediate check
    }

    function stopMonitoring() {
        if (monitoringIntervalId) {
            clearInterval(monitoringIntervalId);
            monitoringIntervalId = null;
        }
        monitoredSlots = [];
        startMonitoringBtn.style.display = 'inline-block';
        stopMonitoringBtn.style.display = 'none';
        updateMonitoringStatus("Monitoring stopped by user.");
    }

    async function pollAllSelectedSlots() {
        if (monitoredSlots.length === 0) {
            stopMonitoring(); // Should not happen if interval is running, but good check
            return;
        }
        updateMonitoringStatus(`Checking ${monitoredSlots.length} slot(s)... Last check: ${new Date().toLocaleTimeString()}`);

        for (const slot of monitoredSlots) {
            // Call backend to check individual slot availability
            // This requires a new backend endpoint: /api/check_slot_availability
            const backendBaseUrl = 'http://localhost:8080';
            const checkUrl = `${backendBaseUrl}/api/check_slot_availability?direction=${slot.direction}&date=${slot.departureDate}&event_uid=${slot.eventUid}`;

            try {
                const response = await fetch(checkUrl); // No auth header needed
                if (!response.ok) {
                    console.error(`Error checking slot ${slot.eventUid}: ${response.status}`);
                    // Optionally update UI for this specific slot's error
                    continue; // Move to next slot
                }
                const availabilityData = await response.json();

                const carsAvailableDisplay = document.querySelector(`#trip-${slot.eventUid} + label .cars-count`);
                if(carsAvailableDisplay) carsAvailableDisplay.textContent = availabilityData.available_cars;


                if (availabilityData.is_available && availabilityData.available_cars > 0) {
                    updateMonitoringStatus(`Slot ${formatTime(slot.dtstartUtcIso)} has ${availabilityData.available_cars} car(s)! Attempting to book...`);
                    // Pass all necessary data to handleAttemptAddToCart
                    await handleAttemptAddToCart({
                        original_event_data: slot.originalEventData, // This is the full event object
                        direction: slot.direction,
                        departureDate: slot.departureDate,
                        pricelistCode: slot.pricelistCode,
                        numCars: currentUserDetails.numCars, // Always 1 car as per new logic
                        numAdults: currentUserDetails.numAdults,
                        userEmail: currentUserDetails.userEmail,
                        userPhone: currentUserDetails.userPhone,
                        vehicleRegNr: currentUserDetails.vehicleRegNr
                    });
                    // If booking attempt is made (successful or not), stop monitoring to prevent re-booking.
                    // More sophisticated logic could retry on certain failures.
                    stopMonitoring();
                    break; // Stop polling other slots once one is found and booking is attempted
                }
            } catch (error) {
                console.error(`Error polling slot ${slot.eventUid}:`, error);
                updateMonitoringStatus(`Error polling slot ${formatTime(slot.dtstartUtcIso)}. Will retry.`);
            }
        }
    }


    async function handleAttemptAddToCart(data) {
        // Ensure essential user details are present before proceeding
        if (!data.userEmail || !data.userPhone) {
            showError("Error: Email or Phone missing for booking attempt.");
            updateMonitoringStatus("Error: Email/Phone missing for booking attempt. Monitoring stopped for this slot.");
            return;
        }
        // vehicleRegNr is now part of currentUserDetails and passed in `data`
        if (data.numCars > 0 && !data.vehicleRegNr) {
            showError("Error: Vehicle Registration Number missing for car booking attempt.");
            updateMonitoringStatus("Error: Vehicle Reg Nr missing. Monitoring stopped for this slot.");
            return;
        }

        // Use dtstart from the original_event_data for more accuracy if available
        const startTimeForDisplay = data.original_event_data.dtstart || data.dtstart_utc_iso;
        showError(`Attempting to book slot: ${formatTime(startTimeForDisplay)}...`);
        updateMonitoringStatus(`Attempting to book slot: ${formatTime(startTimeForDisplay)}...`);
        console.log("Attempting to add to cart with data:", data);

        const { original_event_data, direction, departureDate, pricelistCode, numCars, numAdults, userEmail, userPhone, vehicleRegNr } = data;

        const backendBaseUrl = 'http://localhost:8080';
        const addToCartUrl = `${backendBaseUrl}/api/add_to_cart`;

        try {
            const response = await fetch(addToCartUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                    // Authorization header removed
                },
                body: JSON.stringify({
                    original_event_data: original_event_data,
                    direction: direction,
                    departureDate: departureDate,
                    pricelistCode: pricelistCode,
                    numCars: numCars,
                    numAdults: numAdults,
                    userEmail: userEmail,     // Ensure these are explicitly included
                    userPhone: userPhone,     // Ensure these are explicitly included
                    vehicleRegNr: vehicleRegNr  // Ensure this is explicitly included
                })
            });

            const responseData = await response.json();

            if (!response.ok) {
                // Use error from JSON response if available, otherwise default
                throw new Error(responseData.error || `Error adding to cart: ${response.status} ${response.statusText}`);
            }

            if (responseData.checkoutUrl) {
                console.log("Attempting to open checkout URL:", responseData.checkoutUrl); // DEBUG
                alert("Check console for checkout URL. Will attempt to open: " + responseData.checkoutUrl); // DEBUG
                resultsContainer.innerHTML += `<p class="success-message">Successfully created booking. <a href="${responseData.checkoutUrl}" target="_blank">Proceed to Checkout on Praamid.ee (Booking UID: ${responseData.bookingUid})</a></p>`;
                const newTab = window.open(responseData.checkoutUrl, '_blank');
                if (newTab) {
                    showError('Successfully initiated booking. Opened Praamid.ee checkout page...');
                } else {
                    showError('Could not open new tab. Please check your popup blocker. Checkout URL: ' + responseData.checkoutUrl);
                    resultsContainer.innerHTML += `<p class="error-message">Could not open new tab. Popup blocker? <a href="${responseData.checkoutUrl}" target="_blank">Manual Checkout Link (Booking UID: ${responseData.bookingUid})</a></p>`;
                }
            } else {
                 resultsContainer.innerHTML += `<p class="success-message">${responseData.message || 'Request processed. Booking UID: ' + responseData.bookingUid + '. Please verify on Praamid.ee.'}</p>`;
                showError(responseData.message || 'Successfully added to cart (UID: ' + responseData.bookingUid + '). Please check Praamid.ee.');
            }
        } catch (error) {
            console.error('Failed to add to cart:', error);
            showError(`Failed to add to cart: ${error.message}`);
            resultsContainer.innerHTML += `<p class="error-message">Failed to add to cart: ${error.message}</p>`;
        }
    }


    function formatTime(isoString) {
        if (!isoString) return "N/A";
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString(navigator.language || 'en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZoneName: 'short' });
        } catch (e) {
            console.error("Error formatting date:", isoString, e);
            const timePart = isoString.substring(11, 16);
            return timePart || "N/A";
        }
    }

    function showError(message) {
        errorMessagesDiv.textContent = message;
        errorMessagesDiv.style.display = 'block';
    }

    function clearMessages() {
        errorMessagesDiv.textContent = '';
        errorMessagesDiv.style.display = 'none';
    }

});
