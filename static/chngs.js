// Open the Update Information Modal
function openModal() {
    document.getElementById("Modal").style.display = "flex";
    setTimeout(function() {
        realInitMap('modal-map');
    }, 300); // Wait for modal to become visible
}

// Close the Update Information Modal
function closeModal() {
    document.getElementById("Modal").style.display = "none";
}

// Open the Add Vehicle Modal
function openVehicleModal() {
    document.getElementById("vehicleModal").style.display = "flex";
    trapFocus(document.getElementById("vehicleModal"));
    // Hide all error messages and reset invalid input styles
    document.querySelectorAll('#vehicleModal .error-message').forEach(el => el.style.display = 'none');
    document.querySelectorAll('#vehicleModal .invalid-input').forEach(el => el.classList.remove('invalid-input'));
}

// Close the Add Vehicle Modal
function closeVehicleModal() {
    document.getElementById("vehicleModal").style.display = "none";
}

// Close modal when clicking outside of it
window.onclick = function(event) {
    let updateModal = document.getElementById("Modal");
    let vehicleModal = document.getElementById("vehicleModal");

    if (event.target === updateModal) closeModal();
    if (event.target === vehicleModal) closeVehicleModal();
};

// Add any additional functions from your original chngs.js below

// --- Google Maps Initialization ---
let dashboardMap = null;
let dashboardMarker = null;
let modalMap = null;
let modalMarker = null;

let modalAutocomplete = null;

function realInitMap(containerId = 'display-map') {
    const mapElement = document.getElementById(containerId);
    if (!mapElement || mapElement.offsetWidth === 0 || mapElement.offsetHeight === 0) {
        console.warn(`Map element #${containerId} not ready or not visible!`);
        return;
    }
    // Get coordinates from hidden fields or defaults
    const lat = parseFloat(document.getElementById('latitude')?.value) || 26.9124;
    const lng = parseFloat(document.getElementById('longitude')?.value) || 75.7873;
    const position = { lat, lng };

    // Map options
    const options = {
        center: position,
        zoom: 12,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false
    };

    if (containerId === 'display-map') {
        if (!dashboardMap) {
            dashboardMap = new google.maps.Map(mapElement, options);
            dashboardMarker = new google.maps.Marker({
                position,
                map: dashboardMap,
                draggable: false,
                title: 'Station Location'
            });
        } else {
            dashboardMap.setCenter(position);
            dashboardMarker.setPosition(position);
        }
    } else if (containerId === 'modal-map') {
        // Setup Places Autocomplete for map search
        const input = document.getElementById('map-search');
        if (input && !input._autocompleteInitialized) {
            modalAutocomplete = new google.maps.places.Autocomplete(input);
            modalAutocomplete.addListener('place_changed', function() {
                const place = modalAutocomplete.getPlace();
                if (!place.geometry || !place.geometry.location) return;
                const lat = place.geometry.location.lat();
                const lng = place.geometry.location.lng();
                // Move marker and map
                if (modalMap && modalMarker) {
                    modalMap.setCenter({lat, lng});
                    modalMarker.setPosition({lat, lng});
                }
                document.getElementById('latitude').value = lat;
                document.getElementById('longitude').value = lng;
                // Sync dashboard marker too
                if (dashboardMarker) dashboardMarker.setPosition({lat, lng});
            });
            input._autocompleteInitialized = true;
        }
        if (!modalMap) {
            modalMap = new google.maps.Map(mapElement, options);
            modalMarker = new google.maps.Marker({
                position,
                map: modalMap,
                draggable: true,
                title: 'Drag to set location'
            });
            // Update lat/lng on drag
            modalMarker.addListener('dragend', function() {
                const newPos = modalMarker.getPosition();
                document.getElementById('latitude').value = newPos.lat();
                document.getElementById('longitude').value = newPos.lng();
                // Sync dashboard marker too
                if (dashboardMarker) dashboardMarker.setPosition(newPos);
            });
            // Update marker on map click
            modalMap.addListener('click', function(event) {
                modalMarker.setPosition(event.latLng);
                document.getElementById('latitude').value = event.latLng.lat();
                document.getElementById('longitude').value = event.latLng.lng();
                if (dashboardMarker) dashboardMarker.setPosition(event.latLng);
            });
        } else {
            google.maps.event.trigger(modalMap, 'resize');
            modalMap.setCenter(position);
            modalMarker.setPosition(position);
        }
    }
}
window.initMap = function() { realInitMap('display-map'); };

// Optionally, update dashboard map marker when lat/lng changes
function syncDashboardMapToHiddenFields() {
    const lat = parseFloat(document.getElementById('latitude')?.value);
    const lng = parseFloat(document.getElementById('longitude')?.value);
    if (dashboardMap && dashboardMarker && !isNaN(lat) && !isNaN(lng)) {
        const pos = { lat, lng };
        dashboardMap.setCenter(pos);
        dashboardMarker.setPosition(pos);
    }
}
document.getElementById('latitude')?.addEventListener('change', syncDashboardMapToHiddenFields);
document.getElementById('longitude')?.addEventListener('change', syncDashboardMapToHiddenFields);

// On DOMContentLoaded, initialize dashboard map
window.addEventListener('DOMContentLoaded', function() {
    realInitMap('display-map');
});


function initDisplayMap() {
    // Example: initialize display map in element with id 'display-map'
    var displayMapElement = document.getElementById('display-map');
    if (!displayMapElement) {
        console.warn('Display map element not found!');
        return;
    }
    var displayMap = new google.maps.Map(displayMapElement, {
        center: { lat: 28.6139, lng: 77.2090 },
        zoom: 14
    });
    // Add further logic as needed
}
window.initDisplayMap = initDisplayMap;


// Example placeholder for fetchAndRenderStationQueue (to prevent JS errors)
function fetchAndRenderStationQueue() {
    // TODO: Implement this function
    console.log("fetchAndRenderStationQueue called (placeholder)");
}
