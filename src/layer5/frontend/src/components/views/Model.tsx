import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  ReferenceLine,
} from 'recharts';
import { format } from 'date-fns';
import * as api from '@/services/api';
import * as mockData from '@/services/mockData';
import { Brain, AlertTriangle, CheckCircle2, Calendar, Database, Settings, Activity } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

const parseDates = (obj: any) => {
  if (Array.isArray(obj)) return obj.map(parseDates);
  if (obj && typeof obj === 'object') {
    const out = { ...obj };
    for (const key of Object.keys(out)) {
      if (typeof out[key] === 'string' && /\d{4}-\d{2}-\d{2}T/.test(out[key])) {
        out[key] = new Date(out[key]);
      } else if (typeof out[key] === 'object') {
        out[key] = parseDates(out[key]);
      }
    }
    return out;
  }
  return obj;
};

export function Model() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartsRef = useRef<HTMLDivElement>(null);
  const barsRef = useRef<HTMLDivElement>(null);

  const [modelMeta, setModelMeta] = useState(mockData.getModelMetadata());
  const [modelPerf, setModelPerf] = useState(mockData.getModelPerformance());
  const [calibrationData, setCalibrationData] = useState(mockData.getCalibrationData());
  const [featureImportance, setFeatureImportance] = useState(mockData.getFeatureImportance());
  const [driftAlerts, setDriftAlerts] = useState(mockData.getDriftAlerts());
  const confidenceDeciles = mockData.getConfidenceDeciles();

  useEffect(() => {
    const load = async () => {
      try {
        const meta = await api.fetchModelMetadata();
        setModelMeta(parseDates(meta));
      } catch {
        setModelMeta(mockData.getModelMetadata());
      }
      try {
        const perf = await api.fetchModelPerformance();
        setModelPerf(parseDates(perf));
      } catch {
        setModelPerf(mockData.getModelPerformance());
      }
      try {
        const cal = await api.fetchCalibrationData();
        setCalibrationData(parseDates(cal));
      } catch {
        setCalibrationData(mockData.getCalibrationData());
      }
      try {
        const feat = await api.fetchFeatureImportance();
        setFeatureImportance(parseDates(feat));
      } catch {
        setFeatureImportance(mockData.getFeatureImportance());
      }
      try {
        const drift = await api.fetchDriftAlerts();
        setDriftAlerts(parseDates(drift));
      } catch {
        setDriftAlerts(mockData.getDriftAlerts());
      }
    };
    load();
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Charts entrance
      gsap.fromTo(
        chartsRef.current?.children || [],
        { y: 20, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.35, stagger: 0.1, ease: 'power2.out' }
      );

      // Feature bars animate
      gsap.fromTo(
        barsRef.current?.children || [],
        { scaleX: 0, opacity: 0 },
        {
          scaleX: 1,
          opacity: 1,
          duration: 0.6,
          stagger: 0.05,
          ease: 'power2.out',
          delay: 0.3,
        }
      );
    });

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef} className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="w-6 h-6 text-violet-400" />
          <h2 className="text-xl font-semibold text-[#F3F4F6]">Model Insights</h2>
        </div>
        <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 bg-emerald-500/10">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Model Healthy
        </Badge>
      </div>

      {/* Model Metadata */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
            <Brain className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider">Model</span>
          </div>
          <p className="text-sm font-medium text-[#F3F4F6] truncate">{modelMeta.modelName}</p>
        </div>
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
            <Calendar className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider">Training Date</span>
          </div>
          <p className="text-sm font-medium text-[#F3F4F6]">
            {format(modelMeta.trainingDate, 'yyyy-MM-dd')}
          </p>
        </div>
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
            <Database className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider">Training Data</span>
          </div>
          <p className="text-sm font-medium text-[#F3F4F6]">
            {modelMeta.trainingDataSize.toLocaleString()} trades
          </p>
        </div>
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
            <Settings className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider">Threshold</span>
          </div>
          <p className="text-sm font-medium text-cyan-400">{modelMeta.threshold}</p>
        </div>
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
            <Activity className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider">Version</span>
          </div>
          <p className="text-sm font-medium text-[#F3F4F6]">{modelMeta.version}</p>
        </div>
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-[#A1A7B3] mb-2">
            <CheckCircle2 className="w-4 h-4" />
            <span className="text-xs uppercase tracking-wider">Granularities</span>
          </div>
          <p className="text-sm font-medium text-[#F3F4F6]">
            {modelMeta.supportedGranularities.join(', ')}
          </p>
        </div>
      </div>

      {/* Drift Alerts */}
      {driftAlerts.length > 0 && (
        <div className="space-y-2">
          {driftAlerts.map((alert, index) => (
            <div
              key={index}
              className={`
                flex items-center gap-3 p-3 rounded-lg border
                ${alert.severity === 'critical'
                  ? 'bg-red-500/5 border-red-500/20'
                  : 'bg-amber-500/5 border-amber-500/20'}
              `}
            >
              <AlertTriangle className={`
                w-5 h-5 flex-shrink-0
                ${alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}
              `} />
              <div className="flex-1">
                <p className={`
                  text-sm font-medium
                  ${alert.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}
                `}>
                  {alert.type === 'approval_rate' && 'Approval Rate Drift'}
                  {alert.type === 'calibration' && 'Calibration Shift'}
                  {alert.type === 'distribution' && 'Distribution Anomaly'}
                </p>
                <p className="text-xs text-[#A1A7B3]">{alert.message}</p>
              </div>
              <span className="text-xs text-[#6B7280]">
                {format(alert.timestamp, 'HH:mm')}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Charts Grid */}
      <div ref={chartsRef} className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Confidence Distribution */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Confidence Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={confidenceDeciles}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="decile"
                tickFormatter={(d) => `${d}`}
                stroke="#6B7280"
                fontSize={10}
              />
              <YAxis stroke="#6B7280" fontSize={10} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="tradeCount" fill="#22D3EE" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Calibration Curve */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Calibration Curve</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={calibrationData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="predicted"
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                stroke="#6B7280"
                fontSize={10}
                domain={[0.4, 1]}
              />
              <YAxis
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                stroke="#6B7280"
                fontSize={10}
                domain={[0.4, 1]}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#14161C',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                }}
              />
              <ReferenceLine x={0.535} stroke="#F59E0B" strokeDasharray="3 3" label={{ value: 'Threshold', fill: '#F59E0B', fontSize: 10 }} />
              <ReferenceLine stroke="#6B7280" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#22D3EE"
                strokeWidth={2}
                dot={{ fill: '#22D3EE', strokeWidth: 0, r: 3 }}
                activeDot={{ r: 5 }}
              />
              <Line
                type="linear"
                dataKey="predicted"
                stroke="#6B7280"
                strokeDasharray="3 3"
                strokeWidth={1}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-[#6B7280] text-center">
            45° line = perfect calibration
          </p>
        </div>

        {/* Feature Importance */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
          <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Feature Importance (Top 10)</h3>
          <div ref={barsRef} className="space-y-2">
            {featureImportance.map((feature) => (
              <div key={feature.feature} className="flex items-center gap-3">
                <span className="w-24 text-xs text-[#A1A7B3] truncate">{feature.feature}</span>
                <div className="flex-1 h-4 bg-[#1E2129] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-500 to-cyan-400 rounded-full origin-left"
                    style={{ width: `${feature.importance * 100}%` }}
                  />
                </div>
                <span className="w-10 text-xs text-[#F3F4F6] text-right">
                  {(feature.importance * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Model Performance Table */}
        <div className="bg-[#14161C] rounded-xl border border-white/[0.06] overflow-hidden">
          <div className="px-4 py-3 border-b border-white/[0.06]">
            <h3 className="text-sm font-semibold text-[#F3F4F6]">Model Performance vs Live</h3>
          </div>
          <div className="h-[250px] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-white/[0.06] hover:bg-transparent">
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase">Metric</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Training</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Live (7d)</TableHead>
                  <TableHead className="text-[#A1A7B3] text-[11px] uppercase text-right">Live (30d)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {modelPerf.map((perf) => (
                  <TableRow key={perf.metric} className="border-white/[0.06] text-[#F3F4F6]">
                    <TableCell className="text-xs font-medium">{perf.metric}</TableCell>
                    <TableCell className="text-right text-xs">{(perf.training * 100).toFixed(0)}%</TableCell>
                    <TableCell className={`
                      text-right text-xs
                      ${perf.live7d < perf.training * 0.9 ? 'text-red-400' : 'text-[#F3F4F6]'}
                    `}>
                      {(perf.live7d * 100).toFixed(0)}%
                    </TableCell>
                    <TableCell className={`
                      text-right text-xs
                      ${perf.live30d < perf.training * 0.85 ? 'text-red-400' : 'text-[#F3F4F6]'}
                    `}>
                      {(perf.live30d * 100).toFixed(0)}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>

      {/* Expectancy by Confidence Decile */}
      <div className="bg-[#14161C] rounded-xl border border-white/[0.06] p-4">
        <h3 className="text-sm font-semibold text-[#F3F4F6] mb-4">Expectancy by Confidence Decile</h3>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={confidenceDeciles}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
            <XAxis
              dataKey="decile"
              tickFormatter={(d) => `D${d}`}
              stroke="#6B7280"
              fontSize={10}
            />
            <YAxis
              tickFormatter={(v) => `${v.toFixed(2)}R`}
              stroke="#6B7280"
              fontSize={10}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#14161C',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '8px',
              }}
              formatter={(v: number) => [`${v >= 0 ? '+' : ''}${v.toFixed(2)}R`, 'Expectancy']}
            />
            <ReferenceLine y={0} stroke="#6B7280" />
            <Bar
              dataKey="expectancy"
              fill="#22D3EE"
              radius={[4, 4, 0, 0]}
              fillOpacity={0.8}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
