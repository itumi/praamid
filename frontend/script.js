document.addEventListener('DOMContentLoaded', () => {
    const getScheduleBtn = document.getElementById('getScheduleBtn');
    const resultsContainer = document.getElementById('resultsContainer');
    const authTokenInput = document.getElementById('authToken');
    const directionSelect = document.getElementById('direction');
    const departureDateInput = document.getElementById('departureDate');
    const numCarsInput = document.getElementById('numCars');
    const numAdultsInput = document.getElementById('numAdults');
    const errorMessagesDiv = document.getElementById('errorMessages');
    const tokenHelpLink = document.getElementById('tokenHelpLink');
    const tokenHelpContent = document.getElementById('tokenHelpContent');

    // Set default date to today
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
    const dd = String(today.getDate()).padStart(2, '0');
    departureDateInput.value = `${yyyy}-${mm}-${dd}`;

    if (tokenHelpLink) {
        tokenHelpLink.addEventListener('click', (e) => {
            e.preventDefault();
            const isVisible = tokenHelpContent.style.display === 'block';
            tokenHelpContent.style.display = isVisible ? 'none' : 'block';
            tokenHelpLink.textContent = isVisible ? '(Show instructions)' : '(Hide instructions)';
        });
    }

    if (getScheduleBtn) {
        getScheduleBtn.addEventListener('click', fetchSchedule);
    }

    async function fetchSchedule() {
        const token = authTokenInput.value;
        const direction = directionSelect.value;
        const date = departureDateInput.value;
        // Values from new inputs - will be used later for addToCart
        // const numCars = parseInt(numCarsInput.value) || 0;
        // const numAdults = parseInt(numAdultsInput.value) || 0;


        clearMessages();
        resultsContainer.innerHTML = '<p>Loading schedule...</p>';

        if (!token) {
            showError('Authorization Token is required.');
            resultsContainer.innerHTML = '<p>Please enter the Authorization Token.</p>';
            return;
        }
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
                    'Authorization': token.startsWith('Bearer ') ? token : `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                let errorMsg = `Error fetching schedule: ${response.status} ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    errorMsg += ` - ${errorData.error || 'Unknown server error'}`;
                } catch (e) {
                    // Ignore if error response is not JSON
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();
            displaySchedule(data, direction, date); // Pass date for addToCart

        } catch (error) {
            console.error('Failed to fetch schedule:', error);
            resultsContainer.innerHTML = `<p>Failed to load schedule. ${error.message}</p>`;
            showError(`Failed to load schedule. ${error.message}. Ensure backend is running.`);
        }
    }

    function displaySchedule(scheduleData, direction, departureDate) {
        resultsContainer.innerHTML = '';

        if (!scheduleData || scheduleData.length === 0) {
            resultsContainer.innerHTML = '<p>No trips found for the selected date and direction.</p>';
            return;
        }

        scheduleData.forEach(trip => {
            const tripDiv = document.createElement('div');
            tripDiv.classList.add('trip');

            const displayStartTime = trip.startTimeLocal || formatTime(trip.dtstart_utc_iso);
            const displayEndTime = trip.endTimeLocal || formatTime(trip.dtend_utc_iso);

            let carAvailability = trip.capacities && typeof trip.capacities.sv !== 'undefined' ? trip.capacities.sv : "N/A";
            let availabilityText = `Cars: ${carAvailability}`;

            let isAvailable = false;
            if (typeof carAvailability === 'number' && carAvailability > 0) {
                tripDiv.classList.add('available');
                isAvailable = true;
            } else {
                tripDiv.classList.add('unavailable');
            }

            const shipCode = (trip.ship && trip.ship.code) ? trip.ship.code : "N/A";
            const pricelistCode = (trip.pricelist && trip.pricelist.code) ? trip.pricelist.code : null;


            tripDiv.innerHTML = `
                <div class="trip-info">
                    <span class="time">${displayStartTime} - ${displayEndTime} (UTC)</span>
                    <span class="ship">Ship: ${shipCode} (Pricelist: ${pricelistCode || 'N/A'})</span>
                    <span class="availability">${availabilityText}</span>
                </div>
            `;

            if (isAvailable) {
                const attemptCartButton = document.createElement('button'); // Changed from <a> to <button>
                attemptCartButton.classList.add('book-button'); // Re-use styling for now
                attemptCartButton.textContent = 'Attempt to Add to Cart';

                attemptCartButton.addEventListener('click', () => {
                    const numCars = parseInt(numCarsInput.value);
                    const numAdults = parseInt(numAdultsInput.value);
                    if (isNaN(numCars) || numCars < 0 || isNaN(numAdults) || numAdults < 0) {
                        showError("Please enter valid numbers for cars and adults.");
                        return;
                    }
                    if (numCars === 0 && numAdults === 0) {
                        showError("Please specify at least one car or one adult.");
                        return;
                    }
                    // Placeholder for actual API call
                    handleAttemptAddToCart({
                        tripUid: trip.uid, // Assuming backend response includes trip.uid
                        dtstart_utc_iso: trip.dtstart_utc_iso,
                        direction: direction,
                        departureDate: departureDate, // This is the YYYY-MM-DD date
                        pricelistCode: pricelistCode,
                        numCars: numCars,
                        numAdults: numAdults,
                        token: authTokenInput.value
                    });
                });
                tripDiv.appendChild(attemptCartButton);
            }
            resultsContainer.appendChild(tripDiv);
        });
    }

    async function handleAttemptAddToCart(data) {
        clearMessages();
        showError('Attempting to add to cart...');
        console.log("Attempting to add to cart with data:", data);

        const { original_event_data, direction, departureDate, pricelistCode, numCars, numAdults, token } = data;

        const backendBaseUrl = 'http://localhost:8080';
        const addToCartUrl = `${backendBaseUrl}/api/add_to_cart`;

        try {
            const response = await fetch(addToCartUrl, {
                method: 'POST',
                headers: {
                    'Authorization': token.startsWith('Bearer ') ? token : `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    // Pass original_event_data as the backend expects it for event details
                    original_event_data: original_event_data,
                    direction: direction,
                    departureDate: departureDate, // YYYY-MM-DD
                    pricelistCode: pricelistCode,
                    numCars: numCars,
                    numAdults: numAdults
                    // vehicleRegNr can be added here if collected from UI
                })
            });

            const responseData = await response.json(); // Attempt to parse JSON regardless of response.ok

            if (!response.ok) {
                // Use error from JSON response if available, otherwise default
                throw new Error(responseData.error || `Error adding to cart: ${response.status} ${response.statusText}`);
            }

            if (responseData.checkoutUrl) {
                resultsContainer.innerHTML += `<p class="success-message">Successfully created booking. <a href="${responseData.checkoutUrl}" target="_blank">Proceed to Checkout on Praamid.ee (Booking UID: ${responseData.bookingUid})</a></p>`;
                window.open(responseData.checkoutUrl, '_blank');
                showError('Successfully initiated booking. Opening Praamid.ee checkout page...');
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
