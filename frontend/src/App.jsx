import React, { useState, useEffect, useRef } from 'react';
import {
  MapPin, Navigation, Calendar, Clock, AlertTriangle,
  Download, ArrowRight, Truck, Shield, Route, RefreshCw, Eye, List,
  Sun, Moon, Sparkles
} from 'lucide-react';

function App() {
  // ============================================
  // THEME STATE
  // ============================================
  const [theme, setTheme] = useState('light'); // 'light' | 'dark'

  // Load theme from localStorage on mount
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
    document.documentElement.setAttribute('data-theme', savedTheme);
  }, []);

  // Toggle theme
  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  // ============================================
  // INPUT STATES
  // ============================================
  const [currentLocation, setCurrentLocation] = useState('Dallas, TX');
  const [pickupLocation, setPickupLocation] = useState('El Paso, TX');
  const [dropoffLocation, setDropoffLocation] = useState('Los Angeles, CA');
  const [cycleUsed, setCycleUsed] = useState(20.0);
  const [startTime, setStartTime] = useState(() => {
    const d = new Date();
    d.setHours(8, 0, 0, 0);
    const tzoffset = d.getTimezoneOffset() * 60000;
    const localISOTime = (new Date(d.getTime() - tzoffset)).toISOString().slice(0, 16);
    return localISOTime;
  });
  const [speedMph, setSpeedMph] = useState(55);

  const [carrierName, setCarrierName] = useState('Spotter Logistics LLC');
  const [mainOffice, setMainOffice] = useState('123 Main St, Dallas, TX');
  const [homeTerminal, setHomeTerminal] = useState('456 Safety Rd, Dallas, TX');
  const [truckTrailer, setTruckTrailer] = useState('Truck #101 / Trailer #202');

  // ============================================
  // APP STATES
  // ============================================
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [activeTab, setActiveTab] = useState('map');
  const [selectedDayIndex, setSelectedDayIndex] = useState(0);

  // Map Refs
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const pathLayersRef = useRef([]);
  const markerLayersRef = useRef([]);

  // ============================================
  // MAP INITIALIZATION
  // ============================================
  useEffect(() => {
    if (mapContainerRef.current && !mapInstanceRef.current) {
      const L = window.L;
      if (L) {
        mapInstanceRef.current = L.map(mapContainerRef.current).setView([39.8283, -98.5795], 4);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© OpenStreetMap contributors'
        }).addTo(mapInstanceRef.current);
      }
    }
  }, [activeTab]);

  // Redraw Route and Markers
  useEffect(() => {
    const L = window.L;
    if (!L || !mapInstanceRef.current || !result) return;

    pathLayersRef.current.forEach(layer => layer.remove());
    pathLayersRef.current = [];
    markerLayersRef.current.forEach(layer => layer.remove());
    markerLayersRef.current = [];

    const bounds = [];

    const createCustomIcon = (color, text) => {
      return L.divIcon({
        html: `<div style="background-color: ${color}; color: white; border-radius: 50%; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">${text}</div>`,
        className: 'custom-map-icon',
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      });
    };

    if (result.route.leg1.path && result.route.leg1.path.length > 0) {
      const polyline = L.polyline(result.route.leg1.path, {
        color: '#06b6d4',
        weight: 4,
        opacity: 0.8
      }).addTo(mapInstanceRef.current);

      pathLayersRef.current.push(polyline);
      result.route.leg1.path.forEach(coord => bounds.push(coord));
    }

    if (result.route.leg2.path && result.route.leg2.path.length > 0) {
      const polyline = L.polyline(result.route.leg2.path, {
        color: '#8b5cf6',
        weight: 4,
        opacity: 0.8,
        dashArray: '5, 8'
      }).addTo(mapInstanceRef.current);

      pathLayersRef.current.push(polyline);
      result.route.leg2.path.forEach(coord => bounds.push(coord));
    }

    if (result.route.leg1.path && result.route.leg1.path.length > 0) {
      const startCoord = result.route.leg1.path[0];
      const startMarker = L.marker(startCoord, {
        icon: createCustomIcon('#ef4444', 'LOC')
      })
        .bindPopup(`<b>Current Location:</b><br/>${result.route.leg1.from}`)
        .addTo(mapInstanceRef.current);

      markerLayersRef.current.push(startMarker);
    }

    if (result.route.leg2.path && result.route.leg2.path.length > 0) {
      const pickupCoord = result.route.leg2.path[0];
      const pickupMarker = L.marker(pickupCoord, {
        icon: createCustomIcon('#10b981', 'PKP')
      })
        .bindPopup(`<b>Pickup Location:</b><br/>${result.route.leg2.from}<br/><br/><i>1 Hour Loading Stop</i>`)
        .addTo(mapInstanceRef.current);

      markerLayersRef.current.push(pickupMarker);

      const dropoffCoord = result.route.leg2.path[result.route.leg2.path.length - 1];
      const dropoffMarker = L.marker(dropoffCoord, {
        icon: createCustomIcon('#3b82f6', 'DPF')
      })
        .bindPopup(`<b>Dropoff Location:</b><br/>${result.route.leg2.to}<br/><br/><i>1 Hour Unloading & Inspection Stop</i>`)
        .addTo(mapInstanceRef.current);

      markerLayersRef.current.push(dropoffMarker);
    }

    if (bounds.length > 0) {
      mapInstanceRef.current.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [result, activeTab]);

  // ============================================
  // HANDLE SUBMIT
  // ============================================
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    if (!currentLocation.trim() || !pickupLocation.trim() || !dropoffLocation.trim()) {
      setError('Please provide current location, pickup, and dropoff locations.');
      setLoading(false);
      return;
    }

    if (isNaN(cycleUsed) || cycleUsed < 0 || cycleUsed > 70) {
      setError('Hours used in current cycle must be a number between 0 and 70.');
      setLoading(false);
      return;
    }

    if (isNaN(speedMph) || speedMph < 20 || speedMph > 85) {
      setError('Average driving speed must be a number between 20 and 85 mph.');
      setLoading(false);
      return;
    }

    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

      const response = await fetch(`${API_URL}/api/route`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_location: currentLocation,
          pickup_location: pickupLocation,
          dropoff_location: dropoffLocation,
          cycle_used: Number(cycleUsed),
          start_time: startTime,
          speed_mph: Number(speedMph),
          carrier_name: carrierName,
          main_office: mainOffice,
          home_terminal: homeTerminal,
          truck_trailer: truckTrailer
        }),
      });

      const data = await response.json();

      if (data.success) {
        setResult(data);
        setSelectedDayIndex(0);
        setActiveTab('map');
      } else {
        setError(data.error || 'Failed to simulate route and logs.');
      }
    } catch (err) {
      setError('Could not connect to Django backend server. Please verify Django is running.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // ============================================
  // DOWNLOAD LOG
  // ============================================
  const downloadLogImage = (day) => {
    const link = document.createElement('a');
    link.href = day.image_b64;
    link.download = `HOS_Daily_Log_Day_${day.day_index}_${day.date}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // ============================================
  // RENDER
  // ============================================
  return (
    <div className="app-container">
      {/* ============================================
          HEADER WITH THEME TOGGLE
          ============================================ */}
      <header className="header glass-panel animate-fade-in">
        <div>
          <h1>
            <Truck size={32} />
            Spotter HOS Daily Log & Route Planner
          </h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '14px' }}>
            Compliance-first route planning & automatic Driver Daily Log grids
          </p>
        </div>
        <div className="header-meta">
          <Shield size={16} style={{ color: 'var(--color-emerald)' }} />
          <span>Active Driver: Muhammad Fatik Bin Imran</span>

          {/* Theme Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '16px' }}>
            <Sun size={16} style={{ opacity: theme === 'light' ? 1 : 0.3, transition: 'opacity 0.3s' }} />
            <button
              onClick={toggleTheme}
              className="theme-toggle"
              style={{
                background: 'var(--bg-secondary)',
                border: '2px solid var(--border-glass)',
                borderRadius: '30px',
                width: '56px',
                height: '30px',
                cursor: 'pointer',
                position: 'relative',
                transition: 'all 0.3s ease',
                padding: '2px',
                display: 'flex',
                alignItems: 'center'
              }}
            >
              <div
                className="toggle-thumb"
                style={{
                  position: 'absolute',
                  width: '22px',
                  height: '22px',
                  background: 'var(--color-primary)',
                  borderRadius: '50%',
                  transition: 'all 0.3s ease',
                  left: theme === 'dark' ? 'calc(100% - 24px)' : '2px',
                  boxShadow: '0 2px 8px var(--border-glow)'
                }}
              />
            </button>
            <Moon size={16} style={{ opacity: theme === 'dark' ? 1 : 0.3, transition: 'opacity 0.3s' }} />
          </div>
        </div>
      </header>

      {/* ============================================
          MAIN GRID
          ============================================ */}
      <div className="dashboard-grid">

        {/* ============================================
            LEFT: INPUT PANEL
            ============================================ */}
        <section className="glass-panel animate-slide-in" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: '700', borderBottom: '1px solid var(--border-glass)', paddingBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Route size={18} style={{ color: 'var(--color-primary)' }} />
            Trip Configuration
          </h2>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

            {/* Location Fields */}
            <div>
              <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Current Location</label>
              <div style={{ position: 'relative' }}>
                <MapPin size={16} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--color-rose)' }} />
                <input
                  type="text"
                  value={currentLocation}
                  onChange={(e) => setCurrentLocation(e.target.value)}
                  className="glass-input"
                  style={{ paddingLeft: '36px' }}
                  placeholder="City, State"
                />
              </div>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Pickup Location</label>
              <div style={{ position: 'relative' }}>
                <MapPin size={16} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--color-emerald)' }} />
                <input
                  type="text"
                  value={pickupLocation}
                  onChange={(e) => setPickupLocation(e.target.value)}
                  className="glass-input"
                  style={{ paddingLeft: '36px' }}
                  placeholder="City, State"
                />
              </div>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Dropoff Location</label>
              <div style={{ position: 'relative' }}>
                <MapPin size={16} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--color-blue)' }} />
                <input
                  type="text"
                  value={dropoffLocation}
                  onChange={(e) => setDropoffLocation(e.target.value)}
                  className="glass-input"
                  style={{ paddingLeft: '36px' }}
                  placeholder="City, State"
                />
              </div>
            </div>

            {/* HOS / Cycle Fields */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Cycle Used (Hrs)</label>
                <div style={{ position: 'relative' }}>
                  <Clock size={16} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--color-amber)' }} />
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="70"
                    value={cycleUsed}
                    onChange={(e) => setCycleUsed(e.target.value)}
                    className="glass-input"
                    style={{ paddingLeft: '36px' }}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Speed (MPH)</label>
                <div style={{ position: 'relative' }}>
                  <Navigation size={16} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--color-cyan)' }} />
                  <input
                    type="number"
                    min="20"
                    max="85"
                    value={speedMph}
                    onChange={(e) => setSpeedMph(e.target.value)}
                    className="glass-input"
                    style={{ paddingLeft: '36px' }}
                  />
                </div>
              </div>
            </div>

            {/* Start Date Time */}
            <div>
              <label style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Trip Start Time</label>
              <div style={{ position: 'relative' }}>
                <Calendar size={16} style={{ position: 'absolute', left: '12px', top: '12px', color: 'var(--color-purple)' }} />
                <input
                  type="datetime-local"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="glass-input"
                  style={{ paddingLeft: '36px' }}
                />
              </div>
            </div>

            {/* Collapsible Carrier Details */}
            <details style={{ marginTop: '4px' }}>
              <summary style={{ fontSize: '13px', fontWeight: '600', color: 'var(--color-primary)', cursor: 'pointer', outline: 'none', userSelect: 'none' }}>
                Carrier & Truck Details
              </summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px', padding: '12px', borderLeft: '2px solid var(--border-glass)' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Carrier Name</label>
                  <input type="text" value={carrierName} onChange={(e) => setCarrierName(e.target.value)} className="glass-input" style={{ padding: '6px 10px', fontSize: '13px' }} />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Main Office Address</label>
                  <input type="text" value={mainOffice} onChange={(e) => setMainOffice(e.target.value)} className="glass-input" style={{ padding: '6px 10px', fontSize: '13px' }} />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Home Terminal Address</label>
                  <input type="text" value={homeTerminal} onChange={(e) => setHomeTerminal(e.target.value)} className="glass-input" style={{ padding: '6px 10px', fontSize: '13px' }} />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Truck & Trailer IDs</label>
                  <input type="text" value={truckTrailer} onChange={(e) => setTruckTrailer(e.target.value)} className="glass-input" style={{ padding: '6px 10px', fontSize: '13px' }} />
                </div>
              </div>
            </details>

            {/* Error Message */}
            {error && (
              <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--color-rose)', borderRadius: '8px', padding: '10px 12px', color: 'var(--color-rose)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <AlertTriangle size={16} />
                <span>{error}</span>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              style={{ width: '100%', marginTop: '8px' }}
            >
              {loading ? (
                <>
                  <RefreshCw className="animate-spin" size={18} />
                  Simulating HOS & Routes...
                </>
              ) : (
                <>
                  <Sparkles size={18} />
                  Calculate Route & Logs
                </>
              )}
            </button>
          </form>
        </section>

        {/* ============================================
            RIGHT: OUTPUT DASHBOARD
            ============================================ */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Welcome Screen */}
          {!result && !loading && (
            <div className="glass-panel animate-fade-in" style={{ padding: '60px 40px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
              <div style={{ background: 'rgba(var(--color-primary), 0.1)', padding: '20px', borderRadius: '50%', color: 'var(--color-primary)' }}>
                <Route size={48} />
              </div>
              <h2 style={{ fontSize: '22px', fontWeight: '800' }}>No Active Route Plan</h2>
              <p style={{ color: 'var(--text-secondary)', maxWidth: '500px', fontSize: '15px' }}>
                Enter your start, pickup, and dropoff locations along with your initial Hours of Service cycle logs, then click "Calculate Route & Logs" to generate a fully-compliant trip schedule.
              </p>
            </div>
          )}

          {/* Loading Screen */}
          {loading && (
            <div className="glass-panel animate-fade-in" style={{ padding: '80px 40px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}>
              <div className="animate-spin" style={{ color: 'var(--color-primary)', fontSize: '40px' }}>
                <RefreshCw size={48} />
              </div>
              <h2 style={{ fontSize: '20px', fontWeight: '700' }}>Crunching HOS Compliance & Routes</h2>
              <p style={{ color: 'var(--text-secondary)', maxWidth: '400px', fontSize: '14px' }}>
                Querying OSM geocoders, building route nodes, and simulating driver duty status timeline rules under FMCSA HOS regulations...
              </p>
            </div>
          )}

          {/* Result Dashboard */}
          {result && !loading && (
            <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

              {/* Tab Header Controls */}
              <div className="tab-group">
                <button
                  onClick={() => setActiveTab('map')}
                  className={`tab-button ${activeTab === 'map' ? 'active' : ''}`}
                >
                  <Route size={16} />
                  Route & Map
                </button>

                <button
                  onClick={() => setActiveTab('logs')}
                  className={`tab-button ${activeTab === 'logs' ? 'active' : ''}`}
                >
                  <Eye size={16} />
                  Daily Log Sheets ({result.days.length})
                </button>

                <button
                  onClick={() => setActiveTab('timeline')}
                  className={`tab-button ${activeTab === 'timeline' ? 'active' : ''}`}
                >
                  <List size={16} />
                  Trip Timeline
                </button>
              </div>

              {/* Tab Content 1: Map */}
              {activeTab === 'map' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

                  {/* Route Summary Row */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                    <div className="stat-card">
                      <div className="stat-icon" style={{ background: 'rgba(37, 99, 235, 0.1)', color: 'var(--color-primary)' }}>
                        <Navigation size={20} />
                      </div>
                      <div>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Total Distance</span>
                        <strong style={{ fontSize: '18px', fontWeight: '700' }}>{result.route.total_distance_miles} miles</strong>
                      </div>
                    </div>

                    <div className="stat-card">
                      <div className="stat-icon" style={{ background: 'rgba(124, 58, 237, 0.1)', color: 'var(--color-purple)' }}>
                        <Clock size={20} />
                      </div>
                      <div>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Driving Time</span>
                        <strong style={{ fontSize: '18px', fontWeight: '700' }}>{result.route.total_driving_time_hours} hrs</strong>
                      </div>
                    </div>

                    <div className="stat-card">
                      <div className="stat-icon" style={{ background: 'rgba(5, 150, 105, 0.1)', color: 'var(--color-emerald)' }}>
                        <Calendar size={20} />
                      </div>
                      <div>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Total Duration</span>
                        <strong style={{ fontSize: '18px', fontWeight: '700' }}>{result.days.length} Days Logs</strong>
                      </div>
                    </div>
                  </div>

                  {/* Leaflet Map Div */}
                  <div className="glass-panel" style={{ padding: '10px' }}>
                    <div
                      ref={mapContainerRef}
                      style={{ width: '100%', height: '450px', borderRadius: 'var(--radius-sm)' }}
                    />
                  </div>

                  {/* Route Steps Details */}
                  <div className="glass-panel" style={{ padding: '20px' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: '700', borderBottom: '1px solid var(--border-glass)', paddingBottom: '10px', marginBottom: '14px' }}>
                      Planned Route Segments
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                        <div style={{ background: 'rgba(37, 99, 235, 0.1)', color: 'var(--color-primary)', width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: '700' }}>1</div>
                        <div style={{ flex: 1 }}>
                          <h4 style={{ fontSize: '14px', fontWeight: '600' }}>Leg 1: Current position to Pickup Location</h4>
                          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '2px' }}>
                            From: {result.route.leg1.from} <ArrowRight size={12} style={{ display: 'inline', margin: '0 4px' }} /> To: {result.route.leg1.to}
                          </p>
                          <span style={{ fontSize: '11px', color: 'var(--color-primary)', fontWeight: '600', marginTop: '4px', display: 'block' }}>
                            {result.route.leg1.distance_miles} miles | approx. {result.route.leg1.driving_time_hours} hours driving
                          </span>
                        </div>
                      </div>

                      <div style={{ borderLeft: '2px dashed var(--border-glass)', marginLeft: '14px', height: '16px' }} />

                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                        <div style={{ background: 'rgba(124, 58, 237, 0.1)', color: 'var(--color-purple)', width: '28px', height: '28px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: '700' }}>2</div>
                        <div style={{ flex: 1 }}>
                          <h4 style={{ fontSize: '14px', fontWeight: '600' }}>Leg 2: Pickup Location to Dropoff Location</h4>
                          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '2px' }}>
                            From: {result.route.leg2.from} <ArrowRight size={12} style={{ display: 'inline', margin: '0 4px' }} /> To: {result.route.leg2.to}
                          </p>
                          <span style={{ fontSize: '11px', color: 'var(--color-purple)', fontWeight: '600', marginTop: '4px', display: 'block' }}>
                            {result.route.leg2.distance_miles} miles | approx. {result.route.leg2.driving_time_hours} hours driving
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab Content 2: Logs */}
              {activeTab === 'logs' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

                  {/* Day Buttons Carousel */}
                  <div className="day-selector">
                    {result.days.map((day, idx) => (
                      <button
                        key={idx}
                        onClick={() => setSelectedDayIndex(idx)}
                        className={selectedDayIndex === idx ? 'active' : ''}
                      >
                        Day {day.day_index} ({day.date})
                      </button>
                    ))}
                  </div>

                  {/* Log View Card */}
                  {result.days[selectedDayIndex] && (
                    <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

                      {/* Log Header Controls */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-glass)', paddingBottom: '14px' }}>
                        <div>
                          <h3 style={{ fontSize: '18px', fontWeight: '700' }}>Driver Daily Log Sheet - Day {result.days[selectedDayIndex].day_index}</h3>
                          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Log date: {result.days[selectedDayIndex].date}</span>
                        </div>

                        <button
                          onClick={() => downloadLogImage(result.days[selectedDayIndex])}
                          className="btn-primary"
                          style={{ padding: '8px 16px', fontSize: '13px' }}
                        >
                          <Download size={14} />
                          Download Log Sheet
                        </button>
                      </div>

                      {/* Rendered Log Image */}
                      <div className="log-sheet-container">
                        <img
                          src={result.days[selectedDayIndex].image_b64}
                          alt={`Daily Log Day ${selectedDayIndex + 1}`}
                        />
                      </div>

                      {/* Log Recap Stats Row */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginTop: '10px' }}>
                        <div className="stat-card">
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>On Duty Hours Today</span>
                          <strong style={{ fontSize: '20px', fontWeight: '700', color: 'var(--color-primary)' }}>{result.days[selectedDayIndex].recap.hours_on_duty_today} hrs</strong>
                        </div>

                        <div className="stat-card">
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>On Duty Last 7 Days</span>
                          <strong style={{ fontSize: '20px', fontWeight: '700', color: 'var(--color-purple)' }}>{result.days[selectedDayIndex].recap.on_duty_last_7_days} hrs</strong>
                        </div>

                        <div className="stat-card">
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Available Hours Tomorrow</span>
                          <strong style={{ fontSize: '20px', fontWeight: '700', color: 'var(--color-emerald)' }}>{result.days[selectedDayIndex].recap.available_tomorrow} hrs</strong>
                        </div>

                        <div className="stat-card">
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>Miles Driven Today</span>
                          <strong style={{ fontSize: '20px', fontWeight: '700', color: 'var(--color-amber)' }}>{result.days[selectedDayIndex].miles_driven} mi</strong>
                        </div>
                      </div>

                      {/* Hour Grid Totals */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', background: 'var(--bg-glass)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-glass)' }}>
                        <div style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>OFF DUTY (OFF)</span>
                          <strong style={{ fontSize: '16px' }}>{result.days[selectedDayIndex].totals.off_duty} hrs</strong>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>SLEEPER BERTH (SB)</span>
                          <strong style={{ fontSize: '16px' }}>{result.days[selectedDayIndex].totals.sleeper} hrs</strong>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>DRIVING (D)</span>
                          <strong style={{ fontSize: '16px' }}>{result.days[selectedDayIndex].totals.driving} hrs</strong>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>ON DUTY (ON)</span>
                          <strong style={{ fontSize: '16px' }}>{result.days[selectedDayIndex].totals.on_duty} hrs</strong>
                        </div>
                      </div>

                      {/* Day Remarks List */}
                      <div>
                        <h4 style={{ fontSize: '15px', fontWeight: '700', marginBottom: '10px' }}>Daily Remarks & Locations</h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          {result.days[selectedDayIndex].remarks.map((remark, rIdx) => (
                            <div
                              key={rIdx}
                              style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-glass)', fontSize: '13px' }}
                            >
                              <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-primary)' }} />
                              <span>{remark}</span>
                            </div>
                          ))}
                          {result.days[selectedDayIndex].remarks.length === 0 && (
                            <p style={{ color: 'var(--text-muted)', fontSize: '13px', fontStyle: 'italic' }}>No duty status changes recorded today (Off duty all day).</p>
                          )}
                        </div>
                      </div>

                    </div>
                  )}

                </div>
              )}

              {/* Tab Content 3: Timeline */}
              {activeTab === 'timeline' && (
                <div className="glass-panel" style={{ padding: '24px' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: '700', borderBottom: '1px solid var(--border-glass)', paddingBottom: '12px', marginBottom: '20px' }}>
                    Complete Trip HOS Duty Timeline
                  </h3>

                  <div className="timeline-container">
                    <div className="timeline-line" />

                    {result.timeline.map((act, idx) => (
                      <div key={idx} className="timeline-item">
                        <div className="timeline-dot" style={{ backgroundColor: act.color }} />

                        <div style={{ width: '120px', flexShrink: 0, paddingLeft: '20px', fontSize: '13px' }}>
                          <span style={{ fontWeight: '700', display: 'block' }}>{act.start}</span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block', marginTop: '2px' }}>{act.date}</span>
                        </div>

                        <div className="timeline-content">
                          <div>
                            <strong style={{ fontSize: '14px', fontWeight: '600', display: 'block' }}>{act.description}</strong>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginTop: '2px' }}>
                              Location: {act.location}
                            </span>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <span
                              style={{
                                display: 'inline-block',
                                padding: '4px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: '700',
                                backgroundColor: `${act.color}15`,
                                color: act.color,
                                border: `1px solid ${act.color}30`
                              }}
                            >
                              {act.status}
                            </span>
                            <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                              Duration: {act.duration}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}

        </div>

      </div>
    </div>
  );
}

export default App;