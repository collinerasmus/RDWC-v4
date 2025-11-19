# Temperature & Chiller Visualization Guide

## Overview

The Chiller page now includes a comprehensive temperature history chart with research-backed visual indicators for optimal cannabis cultivation.

## Features

### 1. Temperature History Chart
- **Real-time data visualization**: Shows water temperature trends over selectable time periods (24h, 7d, 30d, 90d)
- **Cannabis-optimized zones**: Visual indicators for optimal, safe, and critical temperature ranges
- **Chiller operation overlay**: Displays when the chiller compressor is actively cooling

### 2. Temperature Zones (Research-Backed)

#### Optimal Zone (18-20°C) - Green
- **Best for**: Maximum nutrient uptake and root health
- **Dissolved oxygen**: Highest levels for healthy root development
- **Pathogen risk**: Minimal
- **Source**: Industry best practices for DWC/RDWC hydroponic systems

#### Safe Boundaries (16°C / 24°C) - Yellow Lines
- **16°C (Low)**: Below this, plant growth slows, nutrient uptake decreases
- **24°C (High)**: Above this, dissolved oxygen drops significantly, increased pathogen risk
- **Note**: System can operate in this range but performance degrades

#### Critical Limits (14°C / 26°C) - Red Lines
- **14°C (Low)**: Plant stress, severely reduced metabolism
- **26°C (High)**: Serious root rot risk (Pythium), oxygen depletion
- **Action required**: Immediate intervention if temperature reaches these thresholds

### 3. Hailea HS-52A Specifications

Based on research and manufacturer specifications:

**Cooling Capacity**
- Power: 1/6 HP (220-240V, 50Hz)
- Suitable tank volume: 100-600 liters
- Flow rate: 600-2200 L/hour
- Refrigerant: R134a (eco-friendly)

**Compressor Protection** (Built into system)
- **Minimum ON time**: 5 minutes (prevents short cycling)
- **Minimum OFF time**: 10 minutes (compressor oil settling)
- **Temperature differential**: 1-2°C recommended (hysteresis)
- **Rationale**: Extends compressor life, reduces energy consumption, prevents thermal stress

**Installation Best Practices**
- Allow 30cm clearance from walls for ventilation
- Never cover unit during operation
- Install after filtration to protect evaporator
- Use titanium heat exchanger (included) for corrosion resistance

## Chart Interpretation

### Reading the Chart

1. **Blue line**: Current water temperature
2. **Purple dashed line**: Your configured target temperature
3. **Green shaded area**: Optimal temperature zone (18-20°C)
4. **Light green background**: Periods when chiller is actively cooling
5. **Yellow dashed lines**: Safe operating boundaries
6. **Red dashed lines**: Critical temperature limits

### Statistics Panel

The chart includes a statistics summary showing:
- **Average temperature**: Mean temperature over the selected period
- **Min/Max**: Temperature range observed
- **In Optimal %**: Percentage of time spent in 18-20°C zone
- **Chiller runtime**: Total minutes of compressor operation and number of cycles

### Energy Efficiency Indicators

- **Frequent short cycles** (< 5 minutes): May indicate hysteresis too narrow or undersized chiller
- **Long continuous runs** (> 30 minutes): May indicate oversized cooling load or inadequate insulation
- **Optimal pattern**: 5-15 minute cycles with 10+ minute rest periods

## Configuration Recommendations

### Temperature Setpoint Selection

**Vegetative Stage**: 18-20°C
- Promotes vigorous root development
- Supports high metabolic activity
- Optimal nutrient absorption

**Flowering Stage**: 18-20°C
- Maintains consistent environment
- Reduces stress during critical phase
- Same range as vegetative (cannabis preference)

### Hysteresis (Temperature Differential)

**Recommended**: 0.5-1.0°C
- **Too narrow** (< 0.3°C): Excessive cycling, compressor wear
- **Too wide** (> 2.0°C): Temperature swings affect plant metabolism
- **Ideal**: 0.5°C for precise control with adequate compressor protection

### Alert Thresholds

**Conservative Settings**:
- Low alert: 17°C (1°C buffer from optimal)
- High alert: 21°C (1°C buffer from optimal)

**Standard Settings**:
- Low alert: 16°C (at safe boundary)
- High alert: 24°C (at safe boundary)

## Troubleshooting

### Temperature Won't Stay in Optimal Zone

**Possible causes**:
1. **Undersized chiller**: Check if runtime exceeds 60% of total time
2. **Inadequate circulation**: Ensure main pump is running continuously
3. **Poor insulation**: Consider reservoir covers or insulation
4. **High ambient temperature**: Chiller efficiency drops in hot environments

**Solutions**:
- Increase chiller target hysteresis to allow longer cooling cycles
- Verify chiller flow rate matches circulation pump (600-2200 L/h)
- Check for heat sources near reservoir (lights, equipment)

### Frequent Short Cycling

**Possible causes**:
1. **Hysteresis too narrow**: System turning on/off too quickly
2. **Oversized chiller**: Cools too fast relative to thermal mass

**Solutions**:
- Increase hysteresis to 1.0-1.5°C
- Verify minimum OFF time (10 minutes) is being enforced
- Check that compressor protection is active

### Temperature Spikes During Lights-On

**Expected behavior**: 1-2°C rise is normal
- Lights add heat load to grow space
- Some heat transfer to reservoir is unavoidable

**Mitigation**:
- Ensure adequate air circulation in grow space
- Consider reservoir location away from lights
- May need to lower target temp by 0.5-1°C during lights-on periods

## Research Sources

1. **Hailea HS-52A Specifications**: Official manufacturer documentation and distributor technical guides
2. **Cannabis Temperature Requirements**: Industry standards from commercial hydroponic operations
3. **Dissolved Oxygen Levels**: Research on water temperature impact on DO concentration
4. **Compressor Protection**: HVAC best practices for rotary compressor longevity
5. **Root Health Optimization**: Studies on root zone temperature effects on nutrient uptake

## Advanced Features (Future)

Planned enhancements based on user feedback:
- [ ] Energy cost calculation based on runtime
- [ ] Predictive alerts for temperature trends
- [ ] Automatic hysteresis adjustment based on ambient temperature
- [ ] Integration with lights schedule for proactive cooling
- [ ] Comparison charts across multiple grow cycles

## Support

For issues or questions:
1. Check the chart guide panel (blue info box below chart)
2. Review system logs at `/api/chiller/events`
3. Verify sensor readings at `/api/sensors`
4. Consult repository documentation

## Version History

- **v1.0.0** (2025-01-19): Initial implementation with research-backed temperature zones, chiller operation visualization, and statistics panel
