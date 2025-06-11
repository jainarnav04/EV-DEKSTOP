document.querySelector(".save-btn").addEventListener("click", function(event) {
    event.preventDefault(); // Prevent default form submission

    // Gather updated values from the form fields
    let stationName = document.getElementById("stationName").value;
    let operatorName = document.getElementById("operatorName").value;
    let chargingType = document.getElementById("chargingType").value;
    let location = document.getElementById("location").value;
    let totalSlots = document.getElementById("totalSlots").value;
    let availableSlots = document.getElementById("availableSlots").value;
    let chargingRate = document.getElementById("chargingRate").value;

    const requestData = {
        stationName: stationName,
        operatorName: operatorName,
        chargingType: chargingType,
        location: location,
        totalSlots: totalSlots,
        availableSlots: availableSlots,
        chargingRate: chargingRate
    };

    console.log("Sending update request:", requestData); // Debugging

    fetch("/update_station", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message || data.error);
        if (data.message) {
            closeModal();  // Close modal after saving
            window.location.reload();
        }
    })
    .catch(error => console.error("Update Error:", error));
});

// Open the Update Information Modal
function openModal() {
    document.getElementById("Modal").style.display = "flex";
}

// Close the Update Information Modal
function closeModal() {
    document.getElementById("Modal").style.display = "none";
}

// Open the Add Vehicle Modal
function openVehicleModal() {
    document.getElementById("vehicleModal").style.display = "flex";
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
