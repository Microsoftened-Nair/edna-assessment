with open("frontend/src/pages/RunDetails.tsx", "r") as f:
    content = f.read()

import_stmt = """import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid
} from "recharts";
"""
if "recharts" not in content:
    content = content.replace('import { useParams } from "react-router-dom";', 'import { useParams } from "react-router-dom";\n' + import_stmt)

COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#d0ed57']

# We need to inject the charts in the JSX
chart_jsx = """
      {taxStep && taxStep.status === "completed" && taxStep.results && (
        <section className="card" style={{ display: "grid", gap: "16px" }}>
          <div className="section-title">
            <h3>Taxonomic Composition</h3>
          </div>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            {taxStep.results.phylum_distribution && (
              <div style={{ flex: '1 1 400px', minWidth: '400px' }}>
                <h4 style={{textAlign: 'center', marginBottom: '10px'}}>Phylum Distribution</h4>
                <div style={{ height: "300px" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={Object.entries(taxStep.results.phylum_distribution).map(([k, v]) => ({ name: k, value: v }))}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                        label={({name, value}) => `${name} (${value})`}
                      >
                        {Object.entries(taxStep.results.phylum_distribution).map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#d0ed57'][index % 8]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
            
            {taxStep.results.genus_distribution && (
              <div style={{ flex: '1 1 600px', minWidth: '500px' }}>
                <h4 style={{textAlign: 'center', marginBottom: '10px'}}>Top Genera</h4>
                <div style={{ height: "350px" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={Object.entries(taxStep.results.genus_distribution)
                        .map(([k, v]) => ({ name: k, count: v }))
                        .sort((a, b) => (b.count as number) - (a.count as number))
                        .slice(0, 15) // top 15 genera
                      }
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis type="category" dataKey="name" width={100} fontSize={10} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#8884d8" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>
        </section>
      )}
"""

# Extract taxStep at the beginning of the component rendering
tax_step_stmt = """  const taxStep = run.pipeline_steps?.find(s => s.step === "taxonomic_classification");
"""

if "const taxStep =" not in content:
    content = content.replace('const isCompleted = run?.status === "completed";', 'const isCompleted = run?.status === "completed";\n' + tax_step_stmt)

if "Taxonomic Composition" not in content:
    content = content.replace('<section className="card" style={{ display: "grid", gap: "16px" }}>\n        <div className="section-title">\n          <h3>Processing timeline</h3>', chart_jsx + '\n      <section className="card" style={{ display: "grid", gap: "16px" }}>\n        <div className="section-title">\n          <h3>Processing timeline</h3>')

with open("frontend/src/pages/RunDetails.tsx", "w") as f:
    f.write(content)
