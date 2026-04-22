import pandas as pd

# 1. 讀取剛剛生成的 EDA 原始結果
input_file = r'scripts\eda\result\EDA_Clinical_Advanced_Results.csv'
try:
    df = pd.read_csv(input_file)
except FileNotFoundError:
    print(f"❌ 找不到 {input_file}，請確認 EDA 腳本已執行完畢並產出檔案。")
    exit()

# 2. 建立匿名對應關係
# 取得唯一且排序過的 case_name，確保編號的一致性
unique_cases = sorted(df['case_name'].unique())
mapping_data = {
    'original_case_name': unique_cases,
    'subject_id': [f'subject{i+1:02d}' for i in range(len(unique_cases))]
}
mapping_df = pd.DataFrame(mapping_data)

# 3. 生成匿名化的數據報表
# 透過 merge 將匿名 ID 帶入原始數據
anonymized_df = df.merge(mapping_df, left_on='case_name', right_on='original_case_name')

# 移除原始名稱，只保留匿名 ID，並重新命名為 case_name
anonymized_df = anonymized_df.drop(columns=['case_name', 'original_case_name'])
anonymized_df = anonymized_df.rename(columns={'subject_id': 'case_name'})

# 調整欄位順序，確保 ID 在第一列
cols = ['case_name'] + [c for c in anonymized_df.columns if c != 'case_name']
anonymized_df = anonymized_df[cols]

# 4. 儲存檔案 (使用 utf-8-sig 確保 Excel 開啟不亂碼)
anonymized_df.to_csv('EDA_Advanced_Results_Anonymized.csv', index=False, encoding='utf-8-sig')
mapping_df.to_csv('Subject_Advanced_Mapping_Key.csv', index=False, encoding='utf-8-sig')

print("✅ 數據匿名化完成！")
print(f"📂 匿名報表：EDA_Results_Anonymized.csv (這份可以放進論文中)")
print(f"🔐 身份金鑰：Subject_Mapping_Key.csv (⚠ 請妥善保管，這是唯一能對應回原始影片的檔案)")