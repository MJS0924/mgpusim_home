#!/usr/bin/python3
import sqlite3
import os
import csv
import re

results_base = os.path.abspath(os.path.join(os.getcwd(), "..", "results"))
output_csv = "simulation_summary.csv"

def calculate_mpki(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        table_name = "mgpusim_metrics"
        # 분석 결과: Location에 장치 이름, What에 메트릭 종류가 있음
        col_loc = "Location"
        col_what = "What"
        col_val = "Value"

        cursor.execute(f"SELECT {col_loc}, {col_what}, {col_val} FROM {table_name}")
        rows = cursor.fetchall()
        
        total_inst = 0
        total_l1_miss = 0
        total_l2_miss = 0

        for loc, what, val in rows:
            if val is None or val == 0: continue
            
            loc_low = loc.lower()
            what_low = what.lower()

            # 1. GPU 1~5번 데이터만 필터링
            gpu_match = re.search(r"gpu\[([1-5])\]", loc_low)
            if gpu_match:
                # 2. Instruction Count (What 컬럼이 'cu_inst_count')
                if what_low == "cu_inst_count":
                    total_inst += val
                
                # 3. L1 TLB Miss (Location에 'L1'과 'TLB'가 있고, What이 'miss')
                elif "l1" in loc_low and "tlb" in loc_low and what_low == "miss":
                    total_l1_miss += val
                
                # 4. L2 TLB Miss (Location에 'L2TLB'가 있고, What이 'miss')
                elif "l2tlb" in loc_low and what_low == "miss":
                    total_l2_miss += val

        conn.close()

        if total_inst > 0:
            l1_mpki = (total_l1_miss / total_inst) * 1000
            l2_mpki = (total_l2_miss / total_inst) * 1000
            return (int(total_inst), int(total_l1_miss), round(l1_mpki, 4), 
                    int(total_l2_miss), round(l2_mpki, 4))
        else:
            return None
            
    except Exception as e:
        print(f"  [Error] {os.path.basename(db_path)}: {e}")
        return None

def main():
    header = ['Pagesize', 'Policy', 'Benchmark', 'Total_Inst', 'L1_Miss', 'L1_MPKI', 'L2_Miss', 'L2_MPKI']
    data_rows = []

    if not os.path.exists(results_base):
        print(f"Error: Results directory '{results_base}' not found.")
        return

    for pagesize in sorted(os.listdir(results_base)):
        pg_path = os.path.join(results_base, pagesize)
        if not os.path.isdir(pg_path): continue
        for policy in sorted(os.listdir(pg_path)):
            pol_path = os.path.join(pg_path, policy)
            if not os.path.isdir(pol_path): continue
            for file in sorted(os.listdir(pol_path)):
                if file.endswith(".sqlite3"):
                    benchmark = file.split('_')[0]
                    db_path = os.path.join(pol_path, file)
                    print(f"Analyzing: {pagesize} > {policy} > {benchmark}")
                    
                    result = calculate_mpki(db_path)
                    if result:
                        data_rows.append([pagesize, policy, benchmark] + list(result))
                    else:
                        print(f"  [Skip] No valid data in {file}")

    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    print(f"\n✅ Analysis complete. Results saved to: {output_csv}")

if __name__ == "__main__":
    main()